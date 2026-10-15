"""Production-style FastAPI application for Robot BOM & Compatibility Agent."""
from __future__ import annotations
import csv, io, os, json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.bom import bom_table, checks_table, ledger_table
from core.catalog import load_catalog, load_seed, normalize_part, reset_overlay, save_overlay
from core.config import DATA_DIR, load_config, load_spec_defs
from core.export import generate_html_report, generate_markdown_report
from core.live import discover_parts, import_part_from_url, refresh_part
from core.llm import DEFAULT_MODEL, GeminiClient, LLMError
from core.parser import heuristic_parse, parse_requirements
from core.power import analyze_power
from core.rules import load_rules
from core.schemas import Part, Requirements
from core.sourcing import check_prices, clear_cache, find_sources
from core.selector import _make_build, qty_for, select_build
from core.testrunner import load_cases, run_case
from core.tinyfish import TinyFishClient, TinyFishError
from core.wiring import generate_wiring_plan

BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config(); SPEC_DEFS = load_spec_defs()
RULES = load_rules(DATA_DIR / 'rules.yaml', SPEC_DEFS)
app = FastAPI(title='Robot BOM Agent API', version='2.0.0', description='Robot component selection, compatibility validation and engineering reports.')
app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')

# API keys are read from environment/.env by default. Optional UI settings are process-memory only.
_runtime_keys = {'gemini': os.getenv('GEMINI_API_KEY', ''), 'tinyfish': os.getenv('TINYFISH_API_KEY', ''), 'model': os.getenv('GEMINI_MODEL', DEFAULT_MODEL)}
_active: dict[str, Any] = {'requirements': None, 'selection': None, 'build': None, 'ctx': None}

class BuildRequest(BaseModel):
    robot_type: str = 'line_follower'
    budget_inr: float = Field(3000, ge=500, le=200000)
    motor_count: int = Field(2, ge=1, le=2)
    min_runtime_h: float = Field(1, ge=0.1, le=48)
    needs_bluetooth: bool = False
    sensor_channels: int | None = Field(None, ge=1, le=16)

class ParseRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=3000)

class SettingsRequest(BaseModel):
    gemini_api_key: str | None = None
    tinyfish_api_key: str | None = None
    gemini_model: str | None = None

class LiveRefreshRequest(BaseModel):
    category: str
    part_ids: list[str] = Field(min_length=1, max_length=20)
    pages_per_part: int = Field(3, ge=1, le=5)

class DiscoverRequest(BaseModel):
    category: str
    query: str = Field(min_length=3, max_length=500)
    kind: str | None = None

class ImportUrlRequest(BaseModel):
    url: str
    category: str
    kind: str | None = None

class PriceCheckRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=10)

class SwapRequest(BaseModel):
    part_ids: dict[str, str]


def _llm():
    return GeminiClient(_runtime_keys['gemini'], _runtime_keys['model'] or None) if _runtime_keys['gemini'] else None

def _tf():
    return TinyFishClient(_runtime_keys['tinyfish']) if _runtime_keys['tinyfish'] else None

def _part(p: Part):
    d = p.model_dump(mode='json')
    d['price_value'] = p.price.value if p.price else None
    d['price_method'] = p.price.evidence.method if p.price else 'none'
    d['stock_value'] = p.in_stock.value if p.in_stock else None
    d['specs_flat'] = {k: v.value for k, v in p.specs.items()}
    return d

def _build(b):
    if b is None: return None
    power = analyze_power(b, CONFIG)
    wiring = generate_wiring_plan(b)
    bom = bom_table(b).to_dict(orient='records')
    ledger = ledger_table(b, SPEC_DEFS).to_dict(orient='records')
    checks = checks_table(b).to_dict(orient='records')
    return {
      'status': b.status, 'counts': b.counts, 'parts_cost': b.parts_cost, 'shipping_total': b.shipping_total,
      'total': b.total, 'budget_inr': (_active['ctx'] or {}).get('budget_inr'),
      'budget_remaining': ((_active['ctx'] or {}).get('budget_inr', 0) - b.total),
      'parts': {cat: {**_part(p), 'qty': b.qty.get(cat, 1), 'line_total': b.qty.get(cat,1) * (p.price.value if p.price else 0)} for cat,p in b.parts.items()},
      'shipping_rows': b.shipping_rows, 'checks': [{'rule_id':c.rule_id,'title':c.title,'category':c.category,'status':c.status,'message':c.message,'missing':c.missing,'evidence':[e.model_dump(mode='json') for e in c.evidence]} for c in b.checks],
      'bom': bom, 'ledger': ledger, 'power': asdict(power) if power else None,
      'wiring': {'connections':[asdict(x) for x in wiring.connections], 'warnings':wiring.warnings,'assembly_steps':wiring.assembly_steps,'mermaid_diagram':wiring.mermaid_diagram},
    }

@app.get('/', response_class=HTMLResponse)
def home():
    return FileResponse(BASE_DIR / 'static' / 'index.html')

@app.get('/api/health')
def health(): return {'status':'ok','service':'Robot BOM & Compatibility Agent','version':'2.0.0'}

@app.get('/api/meta')
def meta():
    catalog=load_catalog(SPEC_DEFS)
    return {'robot_types': CONFIG['robot_types'], 'categories': {k:{'label':k.title(),'specs':v} for k,v in SPEC_DEFS.items()},
      'catalog_count':len(catalog), 'live_price_count':sum(1 for p in catalog.values() if p.price and p.price.evidence.method=='scraped'),
      'gemini_configured':bool(_runtime_keys['gemini']), 'tinyfish_configured':bool(_runtime_keys['tinyfish']), 'model':_runtime_keys['model']}

@app.get('/api/settings/status')
def settings_status():
    return {'gemini_configured':bool(_runtime_keys['gemini']), 'tinyfish_configured':bool(_runtime_keys['tinyfish']), 'model':_runtime_keys['model']}

@app.post('/api/settings')
def settings(body: SettingsRequest):
    if body.gemini_api_key is not None: _runtime_keys['gemini']=body.gemini_api_key.strip()
    if body.tinyfish_api_key is not None: _runtime_keys['tinyfish']=body.tinyfish_api_key.strip()
    if body.gemini_model is not None: _runtime_keys['model']=body.gemini_model.strip() or DEFAULT_MODEL
    return settings_status()

@app.post('/api/parse')
def parse(body: ParseRequest):
    try:
        llm=_llm()
        if llm: req, notes=parse_requirements(llm.json, body.prompt, CONFIG)
        else:
            req, notes=heuristic_parse(body.prompt, CONFIG)
            notes.insert(0,'Gemini is not configured; used the local keyword parser.')
        if req is None: raise HTTPException(422, 'The robot type could not be mapped to a supported type.')
        return {'requirements':req.model_dump(mode='json'),'notes':notes,'parser':'gemini' if llm else 'keyword'}
    except LLMError as e: raise HTTPException(502, str(e))

@app.post('/api/build')
def build(body: BuildRequest):
    try:
        req=Requirements(**body.model_dump()); ctx=req.to_ctx(CONFIG)
        selection=select_build(load_catalog(SPEC_DEFS), ctx, CONFIG, RULES)
        chosen=selection.chosen
        _active.update({'requirements':req,'selection':selection,'build':chosen,'ctx':ctx})
        return {'message':selection.message,'within_budget':selection.within_budget,'evaluated':selection.evaluated,'truncated':selection.truncated,
          'excluded':selection.excluded,'alternatives':[_build(x) for x in selection.alternatives[:5]], 'rejected_count':len(selection.rejected),
          'chosen':_build(chosen), 'naive':_build(selection.naive) if selection.naive else None,
          'fail_stats':dict(selection.fail_stats)}
    except Exception as e: raise HTTPException(400, f'Build failed: {e}')

@app.get('/api/catalog')
def catalog(category: str | None = None, q: str | None = None):
    parts=list(load_catalog(SPEC_DEFS).values())
    if category: parts=[p for p in parts if p.category==category]
    if q: parts=[p for p in parts if q.lower() in (p.name+' '+p.vendor+' '+p.id).lower()]
    return {'items':[_part(p) for p in parts], 'total':len(parts)}

@app.get('/api/part/{part_id}')
def part_detail(part_id: str):
    p=load_catalog(SPEC_DEFS).get(part_id)
    if not p: raise HTTPException(404,'Part not found')
    return _part(p)

@app.get('/api/part/{part_id}/sources')
def part_sources(part_id: str, refresh: bool = False, min_links: int = 5):
    """TinyFish Search -> at least `min_links` selling links for this part."""
    p=load_catalog(SPEC_DEFS).get(part_id)
    if not p: raise HTTPException(404,'Part not found')
    tf=_tf()
    if not tf: raise HTTPException(400,'TinyFish API key is not configured. Add it in Settings & API keys.')
    try:
        return find_sources(p, tf, CONFIG['allowed_vendor_domains'], target=max(1,min(min_links,8)), refresh=refresh)
    except (TinyFishError, RuntimeError) as e: raise HTTPException(502,f'TinyFish search failed: {e}')

@app.post('/api/part/{part_id}/sources/prices')
def part_source_prices(part_id: str, body: PriceCheckRequest):
    """TinyFish Fetch (live page) -> Gemini extraction -> quote-verified price per link."""
    p=load_catalog(SPEC_DEFS).get(part_id)
    if not p: raise HTTPException(404,'Part not found')
    tf,llm=_tf(),_llm()
    if not tf or not llm: raise HTTPException(400,'Configure both Gemini and TinyFish API keys in Settings first.')
    try: return check_prices(p, body.urls, tf, llm.json, SPEC_DEFS)
    except (TinyFishError, LLMError) as e: raise HTTPException(502,str(e))

@app.post('/api/live/refresh')
def live_refresh(body: LiveRefreshRequest):
    if not (_runtime_keys['gemini'] and _runtime_keys['tinyfish']): raise HTTPException(400,'Configure both Gemini and TinyFish API keys in Settings first.')
    if body.category not in SPEC_DEFS: raise HTTPException(422,'Unknown category')
    catalog=load_catalog(SPEC_DEFS); chosen=[catalog[i] for i in body.part_ids if i in catalog and catalog[i].category==body.category]
    if not chosen: raise HTTPException(422,'No valid parts selected for this category')
    reports=[]; tf=_tf(); llm=_llm()
    for p in chosen:
        try:
            refreshed, report=refresh_part(p, tf, llm.json, SPEC_DEFS, CONFIG['allowed_vendor_domains'], max_pages=body.pages_per_part)
            if refreshed: save_overlay([normalize_part(refreshed,SPEC_DEFS)])
            reports.append({'part':p.name,'report':report})
        except Exception as e: reports.append({'part':p.name,'error':str(e)})
    return {'results':reports}

@app.post('/api/live/discover')
def live_discover(body: DiscoverRequest):
    if not (_runtime_keys['gemini'] and _runtime_keys['tinyfish']): raise HTTPException(400,'Configure both Gemini and TinyFish API keys in Settings first.')
    if body.category not in SPEC_DEFS: raise HTTPException(422,'Unknown category')
    try:
        known={p.url for p in load_catalog(SPEC_DEFS).values() if p.url}
        found, report=discover_parts(body.category,body.query,_tf(),_llm().json,SPEC_DEFS,CONFIG['allowed_vendor_domains'],kind=body.kind,known_urls=known)
        return {'items':[_part(p) for p in found], 'report':report}
    except (TinyFishError,LLMError) as e: raise HTTPException(502,str(e))

@app.post('/api/live/import-url')
def live_import(body: ImportUrlRequest):
    if not (_runtime_keys['gemini'] and _runtime_keys['tinyfish']): raise HTTPException(400,'Configure both Gemini and TinyFish API keys in Settings first.')
    if body.category not in SPEC_DEFS: raise HTTPException(422,'Unknown category')
    try:
        p, report=import_part_from_url(body.url,body.category,_tf(),_llm().json,SPEC_DEFS,kind=body.kind)
        return {'part':_part(p) if p else None,'report':report}
    except (TinyFishError,LLMError) as e: raise HTTPException(502,str(e))

@app.post('/api/catalog/add')
def catalog_add(body: dict):
    try:
        parts=[normalize_part(Part.model_validate(x),SPEC_DEFS) for x in body.get('items',[])]
        if not parts: raise HTTPException(422,'No parts supplied')
        save_overlay(parts); return {'added':len(parts)}
    except HTTPException: raise
    except Exception as e: raise HTTPException(422,str(e))

@app.post('/api/catalog/reset')
def catalog_reset():
    reset_overlay(); clear_cache(); _active.update({'requirements':None,'selection':None,'build':None,'ctx':None})
    return {'status':'reset'}

@app.post('/api/swap')
def swap(body: SwapRequest):
    if not _active.get('build') or not _active.get('ctx'): raise HTTPException(409,'Build a BOM before testing component swaps.')
    catalog=load_catalog(SPEC_DEFS); parts=dict(_active['build'].parts)
    for cat,pid in body.part_ids.items():
        p=catalog.get(pid)
        if p is None or p.category!=cat: raise HTTPException(422,f'Invalid replacement for {cat}')
        parts[cat]=p
    qty={c:qty_for(c,p,_active['ctx']) for c,p in parts.items()}
    b=_make_build(parts,qty,_active['ctx'],CONFIG,RULES)
    return {'build':_build(b),'cost_delta':b.total-_active['build'].total}

@app.get('/api/rules')
def rules():
    return {'items':[{'id':r.id,'category':r.category,'title':r.title,'needs':r.needs,'check':r.check,'when':r.when or ''} for r in RULES]}

@app.post('/api/tests')
def tests():
    seed=load_seed(SPEC_DEFS); results=[run_case(c,seed,RULES,CONFIG) for c in load_cases()]
    return {'passed':sum(1 for r in results if r['ok']),'total':len(results),'items':results}

@app.get('/api/export/{kind}')
def export(kind: str):
    b=_active.get('build'); req=_active.get('requirements'); ctx=_active.get('ctx')
    if not b or not req: raise HTTPException(409,'Build a BOM before exporting reports.')
    if kind=='bom.csv':
        content=bom_table(b).to_csv(index=False); media='text/csv'; filename='robot_bom.csv'
    elif kind=='ledger.csv':
        content=ledger_table(b,SPEC_DEFS).to_csv(index=False); media='text/csv'; filename='evidence_ledger.csv'
    elif kind=='report.md':
        power=analyze_power(b,CONFIG); wiring=generate_wiring_plan(b)
        content=generate_markdown_report(b,req,CONFIG,SPEC_DEFS,power,wiring); media='text/markdown'; filename='robot_report.md'
    elif kind=='report.html':
        content=generate_html_report(b,req,CONFIG,SPEC_DEFS); media='text/html'; filename='robot_report.html'
    else: raise HTTPException(404,'Unknown export format')
    return Response(content=content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"'})

@app.exception_handler(Exception)
async def unhandled_error(request, exc):
    # Keep implementation details out of production responses; log to server console.
    import logging
    logging.getLogger('robot_bom_agent').exception('Unhandled application error', exc_info=exc)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500,content={'detail':'Unexpected server error. Check the application logs.'})
