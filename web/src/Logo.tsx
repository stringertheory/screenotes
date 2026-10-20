import { APP_NAME } from './types';

// The mark's paths, as in docs/logo.svg: a screen with a note on its corner, drawn in currentColor so they follow the theme.
const SCREEN = 'M44 68H15A9 9 0 0 1 6 59V19A9 9 0 0 1 15 10H73A9 9 0 0 1 82 19V38';
const NOTE = 'M56 44H88A6 6 0 0 1 94 50V74L80 88H56A6 6 0 0 1 50 82V50A6 6 0 0 1 56 44ZM59 55H85V61H59ZM59 68H77V74H59Z';

/** The mark beside the name. */
export function Lockup() {
  return <span className="lockup" role="img" aria-label={APP_NAME}><Mark /><span aria-hidden="true">{APP_NAME}</span></span>;
}

export function Mark({ className }: { className?: string }) {
  return <svg className={className} viewBox="-2 -3 100 100" aria-hidden="true"><path d={SCREEN} fill="none" stroke="currentColor" strokeWidth="8" /><path d={NOTE} fill="currentColor" fillRule="evenodd" /></svg>;
}
