import React, { useEffect, useState } from 'react';
import { search, record, summary, heatmap, org, whitespace, collabs } from './api.js';

const TABS = ['Search', 'Dashboards', 'Heatmap', 'Organisations', 'Gaps'];

function Search() {
  const [q, setQ] = useState('lithium extraction');
  const [res, setRes] = useState(null);
  const [detail, setDetail] = useState(null);
  const run = () => search(q).then(setRes);
  useEffect(run, []);
  return (<div>
    <input value={q} onChange={(e) => setQ(e.target.value)} size="50" />
    <button data-testid="search-submit" onClick={run}>Search</button>
    <p>{res ? `${res.count} hits in ${res.elapsed_ms} ms` : '…'}</p>
    <ul>{(res?.results || []).map((h) => (
      <li key={h.id}><a href="#" onClick={(e) => { e.preventDefault(); record(h.id).then(setDetail); }}>{h.title}</a>
        <small> [{h.minerals.join(',')}|{h.stages.join(',')}] score {h.score}</small></li>))}</ul>
    {detail && <pre data-testid="record-detail">{JSON.stringify(detail, null, 1)}</pre>}
  </div>);
}

function Dashboards() {
  const [s, setS] = useState(null);
  useEffect(() => summary().then(setS), []);
  if (!s) return <p>…</p>;
  return (<div>
    <h3>Totals: {s.totals.records} records ({s.totals.patents} patents, {s.totals.rd} R&D, {s.totals.publications} publications)</h3>
    <h4>By mineral</h4><ul>{Object.entries(s.by_mineral).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>
    <h4>By stage</h4><ul>{Object.entries(s.by_stage).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>
    <h4>Top organisations</h4><ul>{s.top_orgs.map((o) => <li key={o.name}>{o.name}: {o.count}</li>)}</ul>
  </div>);
}

function Heatmap() {
  const [h, setH] = useState(null);
  useEffect(() => heatmap().then(setH), []);
  if (!h) return <p>…</p>;
  return (<table border="1"><thead><tr><th>mineral × stage</th>{h.stages.map((s) => <th key={s}>{s}</th>)}</tr></thead>
    <tbody>{h.minerals.map((m) => <tr key={m}><th>{m}</th>{h.stages.map((s) => <td key={s}>{h.cells[m][s]}</td>)}</tr>)}</tbody></table>);
}

function Organisations() {
  const [n, setN] = useState('CSIR-NML');
  const [o, setO] = useState(null);
  const run = () => org(n).then(setO).catch(() => setO({ org: n, record_count: 0, records: [], co_orgs: [] }));
  useEffect(run, []);
  return (<div>
    <input value={n} onChange={(e) => setN(e.target.value)} size="40" />
    <button onClick={run}>Open</button>
    {o && <div><h3>{o.org} ({o.record_count} records)</h3>
      <ul>{o.records.map((r) => <li key={r}>{r}</li>)}</ul>
      <p>Co-filing with: {o.co_orgs.join(', ') || '—'}</p></div>}
  </div>);
}

function Gaps() {
  const [w, setW] = useState(null);
  const [c, setC] = useState(null);
  useEffect(() => { whitespace(10).then(setW); collabs().then(setC); }, []);
  if (!w || !c) return <p>…</p>;
  return (<div>
    <h3>Top white spaces (research vs patenting)</h3>
    <ol>{w.top.map((e) => <li key={e.mineral + e.stage}>{e.mineral} × {e.stage}: {e.patents} patents, {e.research} research{e.neglected ? ' (neglected)' : ''}</li>)}</ol>
    <h3>Collaboration suggestions</h3>
    <ul>{c.suggestions.map((s) => <li key={s.org_a + s.org_b}>{s.org_a} ↔ {s.org_b} ({s.shared_cells.length} shared cells)</li>)}</ul>
  </div>);
}

export default function App() {
  const [tab, setTab] = useState('Search');
  return (<div>
    <h1>MineralIQ</h1>
    <nav>{TABS.map((t) => <button key={t} data-testid={`tab-${t}`} disabled={t === tab} onClick={() => setTab(t)}>{t}</button>)}</nav>
    {tab === 'Search' && <Search />}{tab === 'Dashboards' && <Dashboards />}
    {tab === 'Heatmap' && <Heatmap />}{tab === 'Organisations' && <Organisations />}
    {tab === 'Gaps' && <Gaps />}
  </div>);
}
