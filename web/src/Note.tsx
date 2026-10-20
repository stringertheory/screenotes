import { useCallback, useEffect, useRef, useState } from 'react';
import type { Note } from './types';
import { post } from './types';

// How long typing pauses before the note is saved.
const SAVE_DELAY = 600;
type State = '' | 'saving' | 'saved' | 'error';
const LABELS: Record<State, string> = { '': '', saving: 'Saving…', saved: 'Saved', error: 'Not saved. Keep typing to retry.' };

/** The note on one image, saved as it is typed and whenever it is left. Keyed by image, so moving to another image
 *  saves this one first. */
export default function NoteEditor({ id, note }: { id: string; note: Note | null }) {
  const [text, setText] = useState(note?.text ?? '');
  const [state, setState] = useState<State>('');
  const saved = useRef(note?.text ?? '');
  const latest = useRef(text);
  const timer = useRef<number | undefined>(undefined);
  const save = useCallback(async () => {
    window.clearTimeout(timer.current);
    const value = latest.current;
    if (value === saved.current) return;
    setState('saving');
    try {
      await post(`/api/images/${id}/note`, { text: value });
      saved.current = value;
      setState(latest.current === value ? 'saved' : 'saving');
    } catch { setState('error'); }
  }, [id]);
  useEffect(() => () => { void save(); }, [save]);
  return <section className="note" aria-label="Note">
    <label className="sr-only" htmlFor="note">Note</label>
    <textarea id="note" value={text} placeholder="Why did you take this?" rows={4} maxLength={10_000}
      onChange={e => { setText(e.target.value); latest.current = e.target.value; window.clearTimeout(timer.current); timer.current = window.setTimeout(() => void save(), SAVE_DELAY); }}
      onBlur={() => void save()}
      // Arrows, ⌘C and the rest belong to the text while typing, not to the viewer.
      onKeyDown={e => { if (e.key !== 'Escape') e.stopPropagation(); }} />
    <p className={state === 'error' ? 'note-status error-copy' : 'note-status'} role="status">{LABELS[state]}</p>
  </section>;
}
