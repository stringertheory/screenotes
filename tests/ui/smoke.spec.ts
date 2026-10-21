import { existsSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { FIXTURE } from './server';

const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

async function filter(page: Page, label: string, value: string) {
  await page.getByRole('button', { name: /^Filters/ }).click();
  const panel = page.getByRole('dialog', { name: 'Filters' });
  // The folder and type lists are disabled until their facets arrive.
  await expect(panel.getByLabel(label)).toBeEnabled();
  await panel.getByLabel(label).selectOption(value);
  await panel.getByRole('button', { name: 'Apply' }).click();
  await expect(panel).toBeHidden();
}

test('opens a folder and browses, filters, maps and searches it', async ({ page }) => {
  const meta = page.locator('.library-meta p');
  const pictures = page.getByRole('button', { name: /^Open / });

  await test.step('welcome screen', async () => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Choose a folder of images' })).toBeVisible();
  });

  await test.step('open the folder, without setting up visual search', async () => {
    await page.getByRole('checkbox', { name: /Set up visual search too/ }).uncheck();
    await page.getByPlaceholder('~/Pictures').fill(process.env.ORCHARD_UI_PHOTOS!);
    await page.getByRole('button', { name: 'Open', exact: true }).click();
    await expect(page.getByRole('button', { name: 'photos', exact: true })).toBeVisible();
  });

  await test.step('the grid fills', async () => {
    await expect(pictures).toHaveCount(FIXTURE.images);
    await expect(meta).toHaveText(plural(FIXTURE.images, 'image'));
  });

  await test.step('the viewer opens, steps to the next image and closes', async () => {
    await pictures.first().click();
    const viewer = page.getByRole('dialog', { name: 'Image viewer' });
    const name = viewer.getByRole('heading', { level: 1 });
    const first = await name.textContent();
    await expect(viewer.locator('img').first()).toBeVisible();
    await viewer.getByRole('button', { name: 'Next image' }).click();
    await expect(name).not.toHaveText(first!);
    await page.keyboard.press('Escape');
    await expect(viewer).toBeHidden();
  });

  await test.step('filters narrow the grid by folder, type and date', async () => {
    await filter(page, 'Folder', 'trips');
    await expect(meta).toHaveText(`${plural(FIXTURE.trips, 'image')} · in trips`);
    await expect(pictures).toHaveCount(FIXTURE.trips);
    await filter(page, 'Folder', '');
    await filter(page, 'File type', 'image/bmp');
    await expect(meta).toHaveText(`${plural(1, 'image')} · BMP`);
    await filter(page, 'File type', '');
    await filter(page, 'Date', 'year');
    await expect(meta).toHaveText(`${plural(FIXTURE.today, 'image')} · Past year`);
    await filter(page, 'Date', 'all');
    await expect(meta).toHaveText(plural(FIXTURE.images, 'image'));
  });

  await test.step('the map offers to set up visual search, since there is no model', async () => {
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Your folder, laid out by look' })).toBeVisible();
    await page.getByRole('button', { name: 'Grid', exact: true }).click();
    await expect(pictures).toHaveCount(FIXTURE.images);
  });

  await test.step('typed searches match file names', async () => {
    await expect(page.getByRole('textbox', { name: 'Search images' })).toHaveAttribute('placeholder', 'Search text and notes');
    await page.getByRole('textbox', { name: 'Search images' }).fill('beach');
    await page.keyboard.press('Enter');
    await expect(meta).toHaveText(plural(1, 'match', 'matches'));
    await expect(pictures).toHaveCount(1);
    await expect(pictures.first()).toHaveAccessibleName('Open beach.png');
    // The map counts the same file-name matches it lights.
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await expect(meta).toHaveText(plural(1, 'match', 'matches'));
    await page.getByRole('button', { name: 'Grid', exact: true }).click();
    await page.getByRole('button', { name: 'Clear search' }).click();
    await expect(pictures).toHaveCount(FIXTURE.images);
  });

  await test.step('Cmd or Ctrl and Z undo and redo searches', async () => {
    const box = page.getByRole('textbox', { name: 'Search images' });
    await box.fill('red');
    await page.keyboard.press('Enter');
    await expect(pictures).toHaveCount(1);
    await box.fill('beach');
    await page.keyboard.press('Enter');
    await expect(pictures.first()).toHaveAccessibleName('Open beach.png');
    // The search bar still holds the search shown, so the keys step through searches there too.
    await page.keyboard.press('ControlOrMeta+z');
    await expect(box).toHaveValue('red');
    await expect(pictures.first()).toHaveAccessibleName('Open red.png');
    await pictures.first().focus();
    await page.keyboard.press('ControlOrMeta+Shift+z');
    await expect(box).toHaveValue('beach');
    await expect(pictures.first()).toHaveAccessibleName('Open beach.png');
    await expect(page).toHaveURL(/\?q=beach$/);
    // Words typed since are undone first, leaving the search alone.
    await box.press('End');
    await page.keyboard.type('es');
    await page.keyboard.press('ControlOrMeta+z');
    await expect(box).toHaveValue('beach');
    await expect(pictures.first()).toHaveAccessibleName('Open beach.png');
    // Clearing is a step too.
    await page.getByRole('button', { name: 'Clear search' }).click();
    await expect(pictures).toHaveCount(FIXTURE.images);
    await pictures.first().focus();
    await page.keyboard.press('ControlOrMeta+z');
    await expect(pictures).toHaveCount(1);
    await page.keyboard.press('ControlOrMeta+Shift+z');
    await expect(pictures).toHaveCount(FIXTURE.images);
    await expect(box).toHaveValue('');
  });

  await test.step('slash goes to the search bar from the grid, the viewer and the map', async () => {
    const box = page.getByRole('textbox', { name: 'Search images' });
    const selection = () => box.evaluate((input: HTMLInputElement) => input.value.slice(input.selectionStart!, input.selectionEnd!));
    await box.fill('red');
    await pictures.first().focus();
    await page.keyboard.press('/');
    await expect(box).toBeFocused();
    await expect(box).toHaveValue('red');
    expect(await selection()).toBe('red');
    // In the search bar, a slash is typed like any other character.
    await page.keyboard.press('/');
    await expect(box).toHaveValue('/');
    await box.fill('');
    // Held with a modifier, or typed in another field, a slash is left alone.
    await pictures.first().focus();
    await page.keyboard.press('Control+/');
    await expect(box).not.toBeFocused();
    await page.getByRole('button', { name: 'photos', exact: true }).click();
    const path = page.getByRole('dialog', { name: 'Folder' }).getByPlaceholder('~/Pictures');
    await path.fill('~');
    await page.keyboard.press('/');
    await expect(path).toHaveValue('~/');
    await page.keyboard.press('Escape');

    await pictures.first().click();
    const viewer = page.getByRole('dialog', { name: 'Image viewer' });
    await expect(viewer).toBeVisible();
    await page.keyboard.press('/');
    await expect(viewer).toBeHidden();
    await expect(box).toBeFocused();

    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await page.keyboard.press('/');
    await expect(box).toBeFocused();
    await page.getByRole('button', { name: 'Grid', exact: true }).click();
  });

  await test.step('a note typed in a linked viewer outlasts the status polls', async () => {
    const id = (await pictures.nth(1).locator('img').getAttribute('src'))!.split('/').at(-2)!;
    await page.goto(`/?image=${id}`);
    const note = page.getByRole('dialog', { name: 'Image viewer' }).getByRole('textbox', { name: 'Note' });
    await note.click();
    // The page polls its status every few seconds; each poll used to rebuild the note box.
    for (const word of ['why ', 'I ', 'took ', 'this']) { await page.keyboard.type(word); await page.waitForTimeout(1500); }
    await expect(note).toHaveValue('why I took this');
    await expect(note).toBeFocused();
    await note.fill('');
    await note.blur();
  });
});

// After the smoke test, which starts from the welcome screen, since both use the one server.
test('draws on a screenshot in Excalidraw and keeps the drawing as an SVG beside it', async ({ page }) => {
  const folder = process.env.ORCHARD_UI_PHOTOS!;
  const drawing = join(folder, 'red.svg');
  rmSync(drawing, { force: true });
  const problems: string[] = [];
  // Excalidraw lists a CDN after each of its fonts, which the page's policy blocks. Chrome reports every blocked source
  // as the font is declared, though the copy served here loads first.
  page.on('console', message => { if (message.type() === 'error' && !/^Loading the font 'https:\/\/esm\.sh\//.test(message.text())) problems.push(message.text()); });
  page.on('pageerror', error => problems.push(error.message));

  await page.request.post('/api/folder', { data: { path: folder } });
  // The folder is scanned in the background.
  let id = '';
  await expect.poll(async () => (id = (await (await page.request.get('/api/images?q=red&mode=name')).json()).items?.[0]?.id ?? '')).not.toBe('');
  await page.goto(`/?image=${id}`);
  const viewer = page.getByRole('dialog', { name: 'Image viewer' });
  const canvas = page.locator('.annotator canvas.interactive');

  await test.step('draw a rectangle that reaches past the screenshot and save it', async () => {
    await viewer.getByRole('button', { name: 'Draw on it' }).click();
    await expect(canvas).toBeVisible();
    const box = (await canvas.boundingBox())!;
    // The screenshot is fitted to the window, so the far corner is past its edge.
    await page.keyboard.press('r');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width - 80, box.y + box.height - 8, { steps: 5 });
    await page.mouse.up();
    // Escape belongs to the editor, which deselects; the viewer stays open.
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    await expect(canvas).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();
    await expect(canvas).toBeHidden();
  });

  await test.step('the SVG links to the screenshot, holds the scene, and is in its pixels', async () => {
    const svg = readFileSync(drawing, 'utf8');
    expect(svg).toContain('<!-- svg-source:excalidraw -->');
    expect(svg).toContain('payload-type:application/vnd.excalidraw+json');
    expect(svg).toContain('href="red.png"');
    expect(svg).not.toContain('data:image/png');
    const [left, top, width, height] = svg.match(/viewBox="([^"]+)"/)![1].split(' ').map(Number);
    expect(left).toBeLessThan(48);
    expect(top).toBeLessThan(48);
    expect(left + width).toBeGreaterThan(48);
    expect(top + height).toBeGreaterThan(48);
  });

  await test.step('the viewer shows the drawing over the screenshot, and hides it', async () => {
    await expect(viewer.locator('svg.drawn image')).toHaveCount(2);
    await viewer.getByRole('button', { name: 'Hide drawing' }).click();
    await expect(viewer.locator('svg.drawn')).toHaveCount(0);
    await page.keyboard.press('d');
    await expect(viewer.locator('svg.drawn image')).toHaveCount(2);
    await viewer.getByRole('button', { name: 'Edit drawing' }).click();
    await expect(canvas).toBeVisible();
    // Opened unchanged, it closes without asking.
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(canvas).toBeHidden();
  });

  await test.step('the drawing opens again from the SVG and saves the same', async () => {
    const before = readFileSync(drawing, 'utf8').match(/viewBox="([^"]+)"/)![1];
    await viewer.getByRole('button', { name: 'Edit drawing' }).click();
    await expect(canvas).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();
    await expect(canvas).toBeHidden();
    expect(readFileSync(drawing, 'utf8').match(/viewBox="([^"]+)"/)![1]).toBe(before);
  });

  await test.step('its tile in the grid says it has a drawing', async () => {
    await page.keyboard.press('Escape');
    await expect(viewer).toBeHidden();
    await page.getByRole('button', { name: /^Open red\.png, which has a drawing$/ }).click();
    await expect(viewer).toBeVisible();
  });

  await test.step('clearing the drawing removes the SVG', async () => {
    await viewer.getByRole('button', { name: 'Edit drawing' }).click();
    await expect(canvas).toBeVisible();
    await page.keyboard.press('ControlOrMeta+a');
    await page.keyboard.press('Delete');
    await page.getByRole('button', { name: 'Done' }).click();
    await expect(canvas).toBeHidden();
    expect(existsSync(drawing)).toBe(false);
    await expect(viewer.getByRole('button', { name: 'Draw on it' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Open red.png', exact: true })).toBeVisible();
  });

  expect(problems).toEqual([]);
});
