import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Search, Settings } from 'lucide-react';
import type { Picture, Results, Status } from './types';
import { APP_NAME, dateLabel, fileName, imageUrl, post, request, storageKey } from './types';

const LIMITS = [5, 10, 20, 50];
const LIMIT_KEY = storageKey('menu.limit');
// A scan started when the menu opens finds a screenshot taken a moment ago; this is how long the list waits for it.
const SCAN_WAIT = 10_000;
const SEARCH_DELAY = 150;

declare global {
  interface Window { webkit?: { messageHandlers?: Record<string, { postMessage: (message: unknown) => void }> } }
}

/** Ask the menu bar item for something outside the page. In a browser, for working on the page, it opens the same
 *  addresses itself. */
function send(action: 'open' | 'search' | 'home' | 'quit', value = '') {
  const handler = window.webkit?.messageHandlers?.screenotes;
  if (handler) { handler.postMessage({ action, value }); return; }
  if (action === 'quit') return;
  window.open(action === 'open' ? `/?image=${value}` : action === 'search' ? `/?mode=name&q=${encodeURIComponent(value)}` : '/', '_blank');
}

function readLimit() {
  try { const saved = Number(localStorage.getItem(LIMIT_KEY)); return LIMITS.includes(saved) ? saved : 10; } catch { return 10; }
}

/** The popover the menu bar item opens: a search over screenshots' text and notes, and the most recent ones. */
export default function Menu() {
  const [limit, setLimit] = useState(readLimit);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Picture[]>([]);
  const [total, setTotal] = useState(0);
  const [folder, setFolder] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [settings, setSettings] = useState(false);
  const field = useRef<HTMLInputElement>(null);
  const latest = useRef(0);
  const load = useCallback(async (text: string) => {
    const asked = ++latest.current;
    try {
      const status = await request<Status>('/api/status');
      if (asked !== latest.current) return;
      setFolder(!!status.folder);
      if (!status.folder) { setItems([]); return; }
      const data = await request<Results>(`/api/images?${new URLSearchParams({ q: text.trim(), mode: 'name', limit: String(limit) })}`);
      if (asked !== latest.current) return;
      setItems(data.items); setTotal(data.total); setError('');
    } catch (e) { if (asked === latest.current) setError((e as Error).message); }
  }, [limit]);
  const queryRef = useRef(query);
  queryRef.current = query;
  useEffect(() => { const timer = setTimeout(() => void load(query), query ? SEARCH_DELAY : 0); return () => clearTimeout(timer); }, [query, load]);
  useEffect(() => {
    document.documentElement.classList.add('menu-page');
    const dark = matchMedia('(prefers-color-scheme: dark)');
    const theme = () => { document.documentElement.dataset.theme = dark.matches ? 'dark' : 'light'; };
    theme(); dark.addEventListener('change', theme);
    // Each time the popover opens: type straight away, and look for screenshots taken since it last opened.
    const shown = async () => {
      setSettings(false);
      field.current?.focus(); field.current?.select();
      void load(queryRef.current);
      try {
        await post('/api/scan');
        const started = Date.now();
        while (Date.now() - started < SCAN_WAIT) {
          await new Promise(resolve => setTimeout(resolve, 400));
          const status = await request<Status>('/api/status');
          if (status.library?.scan.state !== 'scanning') break;
        }
      } catch { /* The list already shows what the last scan found. */ }
      void load(queryRef.current);
    };
    window.addEventListener('screenotes:shown', shown);
    return () => { window.removeEventListener('screenotes:shown', shown); dark.removeEventListener('change', theme); };
  }, [load]);
  const choose = (next: number) => { setLimit(next); setSettings(false); try { localStorage.setItem(LIMIT_KEY, String(next)); } catch { /* Kept for this session. */ } };
  const searching = !!query.trim();
  return <div className="menu" onKeyDown={e => { if (e.key === 'Escape' && settings) { e.stopPropagation(); setSettings(false); } }}>
    <div className="menu-top">
      <form className="menu-search" role="search" onSubmit={e => { e.preventDefault(); if (query.trim()) send('search', query); }}>
        <Search aria-hidden="true" />
        <label className="sr-only" htmlFor="menu-search">Search all screenshots</label>
        <input ref={field} id="menu-search" type="search" autoFocus value={query} placeholder="Search all screenshots" onChange={e => setQuery(e.target.value)} />
      </form>
      <button className="menu-gear" aria-label="Settings" title="Settings" aria-expanded={settings} onClick={() => setSettings(!settings)}><Settings /></button>
      {settings && <div className="menu-settings" role="menu">
        <button role="menuitem" onClick={() => send('home')}>Open {APP_NAME}</button>
        <hr />
        <p>Screenshots in menu</p>
        {LIMITS.map(value => <button key={value} role="menuitemradio" aria-checked={value === limit} onClick={() => choose(value)}>{value === limit ? <Check /> : <span className="menu-check" />}{value}</button>)}
        <hr />
        <button role="menuitem" onClick={() => send('quit')}>Quit {APP_NAME}</button>
      </div>}
    </div>
    <p className="menu-label">{searching ? (total > items.length ? `${items.length} of ${total.toLocaleString()} matches · Return shows all` : `${total.toLocaleString()} ${total === 1 ? 'match' : 'matches'}`) : 'Recent screenshots'}</p>
    <div className="menu-list">
      {error ? <p className="menu-empty">{error}</p>
        : folder === false ? <p className="menu-empty">No folder is open. <button className="menu-link" onClick={() => send('home')}>Open {APP_NAME}</button> to choose one.</p>
        : folder && !items.length ? <p className="menu-empty">{searching ? 'No screenshots match.' : 'No screenshots yet.'}</p>
        : items.map(item => <button key={item.id} className="menu-shot" title={`${fileName(item.path)}\n${dateLabel(item.date, true)}`} onClick={() => send('open', item.id)}>
          <img src={imageUrl(item.id)} alt={fileName(item.path)} decoding="async" />
        </button>)}
    </div>
  </div>;
}
