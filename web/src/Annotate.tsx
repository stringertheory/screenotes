import { useEffect, useRef, useState } from 'react';
import { Excalidraw, convertToExcalidrawElements, exportToSvg, getCommonBounds, getSceneVersion, loadFromBlob } from '@excalidraw/excalidraw';
import type { BinaryFileData, BinaryFiles, DataURL, ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from '@excalidraw/excalidraw/types';
import type { ExcalidrawElement, FileId } from '@excalidraw/excalidraw/element/types';
import '@excalidraw/excalidraw/index.css';
import type { Annotation } from './types';
import { imageUrl, post } from './types';

declare global { interface Window { EXCALIDRAW_ASSET_PATH?: string } }
// The fonts the build copies in, rather than Excalidraw's CDN.
window.EXCALIDRAW_ASSET_PATH = '/excalidraw/';

// The screenshot is one locked image in the scene, with this id and file id. The page gives Excalidraw its pixels, and
// the saved SVG only its name.
const SCREENSHOT = 'screenshot';
const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';
// A screenshot this many pixels on its longer side is taken as a Retina one, two pixels to a point, and is placed in
// the scene at half size, so Excalidraw's text and lines come out the size they would be on screen. Saving scales back
// to pixels.
const RETINA_WIDTH = 2000;

interface Props {
  id: string; width: number; height: number; annotation: Annotation;
  onSaved: (annotation: Annotation) => void; onClose: () => void;
}

/** Excalidraw over one screenshot. Done saves the drawing as an SVG beside the screenshot; a drawing with nothing in
 *  it removes the SVG. */
export default function Annotator({ id, width, height, annotation, onSaved, onClose }: Props) {
  const [initial, setInitial] = useState<ExcalidrawInitialDataState | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const api = useRef<ExcalidrawImperativeAPI | null>(null);
  const opened = useRef(-1);
  // Read once, when the editor opens: the drawing as saved then, over the screenshot.
  const start = useRef(annotation);
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const density = Math.max(width, height) >= RETINA_WIDTH ? 2 : 1;
    (async () => {
      const shot = await fetchBlob(imageUrl(id, 'display'), signal);
      const saved = start.current.box ? await loadFromBlob(await fetchBlob(annotationUrl(id, start.current), signal), null, null) : null;
      const elements: readonly ExcalidrawElement[] = saved?.elements ?? [];
      const file: BinaryFileData = { id: SCREENSHOT as FileId, dataURL: await dataUrl(shot), mimeType: shot.type as BinaryFileData['mimeType'], created: Date.now() };
      setInitial({
        elements: elements.some(element => element.id === SCREENSHOT) ? elements : [...convertToExcalidrawElements([
          { type: 'image', id: SCREENSHOT, fileId: SCREENSHOT as FileId, x: 0, y: 0, width: width / density, height: height / density, locked: true },
        ], { regenerateIds: false }), ...elements],
        files: { ...saved?.files, [SCREENSHOT]: file },
        appState: { ...saved?.appState, viewBackgroundColor: '#ffffff', theme: 'light' },
        scrollToContent: true,
      });
    })().catch(e => { if (e.name !== 'AbortError') setError(`The drawing could not be opened. ${e.message}`); });
    return () => controller.abort();
  }, [id, width, height]);

  const changed = () => !!api.current && getSceneVersion(api.current.getSceneElements()) !== opened.current;
  const close = () => { if (!changed() || confirm('Close without saving the drawing?')) onClose(); };
  const save = async () => {
    const editor = api.current;
    if (!editor) return;
    setSaving(true); setError('');
    try {
      const svg = await toSvg(editor.getSceneElements(), editor.getFiles(), start.current.image, width);
      onSaved((await post<{ annotation: Annotation }>(`/api/images/${id}/annotation`, { svg })).annotation);
      onClose();
    } catch (e) { setError((e as Error).message); setSaving(false); }
  };

  // Keys belong to the editor, not to the viewer behind it. Escape is the editor's too, so it doesn't close the viewer.
  return <div className="annotator" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') e.preventDefault(); }}>
    {initial ? <Excalidraw initialData={initial} theme="light" name={start.current.image} autoFocus
      excalidrawAPI={editor => { api.current = editor; }}
      onChange={elements => {
        if (opened.current >= 0) return;
        // Once, when the scene is first drawn: what Cancel compares with, and the screenshot fitted to the window.
        opened.current = getSceneVersion(elements);
        api.current?.scrollToContent(undefined, { fitToViewport: true, viewportZoomFactor: 0.9, animate: false });
      }}
      UIOptions={{ canvasActions: { loadScene: false, saveToActiveFile: false, export: false, saveAsImage: false, toggleTheme: false, changeViewBackgroundColor: false } }}
      renderTopRightUI={() => <div className="annotator-actions">
        {error && <p className="error-copy" role="status">{error}</p>}
        <button className="text-button secondary" onClick={close}>Cancel</button>
        <button className="text-button" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Done'}</button>
      </div>} />
      : <div className="empty">{error ? <><p>{error}</p><button className="text-button secondary" onClick={onClose}>Close</button></> : <p>Opening…</p>}</div>}
  </div>;
}

const annotationUrl = (id: string, annotation: Annotation) => `/api/images/${id}/annotation?v=${annotation.modified}`;

/** The drawing as Excalidraw exports it, with the scene inside so excalidraw.com opens it, in the screenshot's pixel
 *  grid, and the screenshot as a link to the file named `image` beside it. Empty when nothing is drawn. */
async function toSvg(elements: readonly ExcalidrawElement[], files: BinaryFiles, image: string, width: number) {
  if (!elements.some(element => element.id !== SCREENSHOT)) return '';
  const shot = elements.find(element => element.id === SCREENSHOT);
  const linked = { ...files, [SCREENSHOT]: { ...files[SCREENSHOT], dataURL: encodeURIComponent(image) as DataURL } };
  const root = await exportToSvg({ elements, files: linked, exportPadding: 0, appState: { exportEmbedScene: true, exportBackground: false, exportWithDarkMode: false } });
  // Excalidraw draws from the scene's top-left corner. Moved back to the screenshot's, so the SVG's numbers are the
  // screenshot's pixels and the viewer can lay it over the image.
  const [minX, minY, maxX, maxY] = getCommonBounds(elements);
  const x = shot?.x ?? 0, y = shot?.y ?? 0, scale = shot ? width / shot.width : 1;
  const group = document.createElementNS(SVG_NS, 'g');
  group.setAttribute('transform', `scale(${scale}) translate(${minX - x} ${minY - y})`);
  for (const child of [...root.children]) if (child.localName !== 'metadata' && child.localName !== 'defs') group.appendChild(child);
  root.appendChild(group);
  const box = [(minX - x) * scale, (minY - y) * scale, (maxX - minX) * scale, (maxY - minY) * scale];
  root.setAttribute('viewBox', box.join(' '));
  root.setAttribute('width', String(box[2]));
  root.setAttribute('height', String(box[3]));
  inlineImages(root);
  return new XMLSerializer().serializeToString(root);
}

/** Each image drawn where it is used, linked with xlink:href. Excalidraw draws images from a <symbol> through <use>
 *  with SVG 2's plain href, and Inkscape shows neither. Browsers read xlink:href as well. */
function inlineImages(root: SVGSVGElement) {
  root.setAttributeNS('http://www.w3.org/2000/xmlns/', 'xmlns:xlink', XLINK_NS);
  for (const use of [...root.querySelectorAll('use')]) {
    const id = use.getAttribute('href')?.replace(/^#/, '');
    const source = id && root.querySelector(`symbol#${CSS.escape(id)} > image`);
    if (!source) continue;
    const image = document.createElementNS(SVG_NS, 'image');
    for (const { name, value } of [...use.attributes]) if (name !== 'href') image.setAttribute(name, value);
    // A cropped image keeps its whole size, and its mask crops it; otherwise it fills the place it is used.
    for (const name of ['width', 'height']) if (!source.getAttribute(name)?.endsWith('%')) image.setAttribute(name, source.getAttribute(name)!);
    image.setAttribute('preserveAspectRatio', 'none');
    image.setAttributeNS(XLINK_NS, 'xlink:href', source.getAttribute('href')!);
    use.replaceWith(image);
  }
  for (const symbol of [...root.querySelectorAll('symbol')]) if (symbol.querySelector(':scope > image')) symbol.remove();
}

async function fetchBlob(url: string, signal: AbortSignal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error('The file is no longer there. Rescan to refresh.');
  return response.blob();
}

const dataUrl = (blob: Blob) => new Promise<DataURL>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result as DataURL);
  reader.onerror = () => reject(reader.error);
  reader.readAsDataURL(blob);
});
