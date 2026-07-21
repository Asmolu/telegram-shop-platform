import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { isPlainSameTabClick } from '../src/shared/navigation/clickSemantics.ts';

const internalLinkSource = readFileSync(
  new URL('../src/shared/navigation/InternalLink.tsx', import.meta.url),
  'utf8',
);
const shellSource = readFileSync(new URL('../src/shared/ui/AppShell.tsx', import.meta.url), 'utf8');
const dashboardSource = readFileSync(
  new URL('../src/pages/Dashboard/DashboardPage.tsx', import.meta.url),
  'utf8',
);
const productsSource = readFileSync(
  new URL('../src/pages/Products/ProductsPage.tsx', import.meta.url),
  'utf8',
);
const looksSource = readFileSync(new URL('../src/pages/Looks/LooksPage.tsx', import.meta.url), 'utf8');
const nginxSource = readFileSync(new URL('../nginx.conf', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

const plainClick = {
  button: 0,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  defaultPrevented: false,
};

test('only a plain primary click is intercepted for same-tab SPA navigation', () => {
  assert.equal(isPlainSameTabClick(plainClick), true);
  assert.equal(isPlainSameTabClick({ ...plainClick, ctrlKey: true }), false);
  assert.equal(isPlainSameTabClick({ ...plainClick, metaKey: true }), false);
  assert.equal(isPlainSameTabClick({ ...plainClick, shiftKey: true }), false);
  assert.equal(isPlainSameTabClick({ ...plainClick, altKey: true }), false);
  assert.equal(isPlainSameTabClick({ ...plainClick, button: 1 }), false);
  assert.equal(isPlainSameTabClick({ ...plainClick, defaultPrevented: true }), false);
});

test('internal link prevents default only for same-tab client navigation', () => {
  assert.match(internalLinkSource, /<a \{\.\.\.props\} href=\{href\} onClick=\{handleClick\}>/);
  assert.match(internalLinkSource, /event\.preventDefault\(\);\s+onNavigate\(href\)/);
  assert.doesNotMatch(internalLinkSource, /onContextMenu/);
  assert.doesNotMatch(internalLinkSource, /onMouseDown/);
  assert.doesNotMatch(internalLinkSource, /window\.open/);
});

test('route-backed navigation surfaces render anchors with href', () => {
  assert.match(shellSource, /<InternalLink[\s\S]*href=\{item\.path\}/);
  assert.match(dashboardSource, /<InternalLink className="dashboard-link" href=\{href\}/);
  assert.match(productsSource, /href="\/products\/new"/);
  assert.match(productsSource, /href=\{`\/products\/\$\{product\.id\}\/edit`\}/);
  assert.match(looksSource, /href="\/looks\/new"/);
  assert.match(looksSource, /href=\{`\/looks\/\$\{look\.id\}\/edit`\}/);
});

test('mutation actions remain buttons', () => {
  assert.match(productsSource, /<button[\s\S]*archiveProduct/);
  assert.match(looksSource, /<button[\s\S]*archiveLook/);
});

test('modified or middle-click navigation cannot change the old tab route', () => {
  let oldTabRoute = '/dashboard';
  const maybeNavigate = (event, href) => {
    if (isPlainSameTabClick(event)) oldTabRoute = href;
  };

  maybeNavigate({ ...plainClick, ctrlKey: true }, '/products');
  maybeNavigate({ ...plainClick, button: 1 }, '/orders');
  assert.equal(oldTabRoute, '/dashboard');
  maybeNavigate(plainClick, '/statistics');
  assert.equal(oldTabRoute, '/statistics');
});

test('direct internal routes use the Nginx SPA fallback', () => {
  assert.match(nginxSource, /try_files \$uri \$uri\/ \/index\.html;/);
  assert.match(appSource, /`\$\{normalized\}\$\{url\.search\}\$\{url\.hash\}`/);
});
