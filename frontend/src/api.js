// Same-origin by default: in dev the Vite proxy forwards the API routes to
// :8000; in production the backend serves this bundle from frontend/dist.
// Set VITE_API_BASE at build time to point at a separately hosted API.
const B = import.meta.env?.VITE_API_BASE || '';

export const j = (p) => fetch(B + p).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
export const search = (q, f = {}) => j(`/search?${new URLSearchParams({ q, ...f })}`);
export const record = (id) => j(`/records/${encodeURIComponent(id)}`);
export const summary = () => j('/dashboard/summary');
export const heatmap = () => j('/heatmap');
export const org = (n) => j(`/orgs/${encodeURIComponent(n)}`);
export const matrix = () => j('/gaps/matrix');
export const whitespace = (top = 10) => j(`/gaps/whitespace?top=${top}`);
export const collabs = () => j('/gaps/collaborations');
