import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const root = process.cwd();
const manifestPath = path.join(root, 'dist', '.vite', 'manifest.json');
const srcDir = path.join(root, 'src');
const requiredLazyPages = [
  'src/pages/CategoriesPage.tsx',
  'src/pages/CategoryPage.tsx',
  'src/pages/SearchPage.tsx',
  'src/pages/SearchResultsPage.tsx',
  'src/pages/ProductDetailPage.tsx',
  'src/pages/CartPage.tsx',
  'src/pages/CheckoutPage.tsx',
  'src/pages/PaymentPage.tsx',
  'src/pages/OrderSuccessPage.tsx',
  'src/pages/ProfilePage.tsx',
  'src/pages/PersonalDataPage.tsx',
  'src/pages/FaqPage.tsx',
  'src/pages/NotFoundPage.tsx',
];

if (!fs.existsSync(manifestPath)) {
  throw new Error('Missing Vite manifest. Run npm run build first.');
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const mainEntryKey = Object.keys(manifest).find((key) => manifest[key]?.isEntry);
const mainEntry = mainEntryKey ? manifest[mainEntryKey] : null;

if (!mainEntry?.isEntry) {
  throw new Error('Missing application entry in Vite manifest.');
}

const staticImports = new Set();
const visitStaticImport = (key) => {
  if (!key || staticImports.has(key)) {
    return;
  }
  staticImports.add(key);
  for (const child of manifest[key]?.imports ?? []) {
    visitStaticImport(child);
  }
};

for (const key of mainEntry.imports ?? []) {
  visitStaticImport(key);
}

const lazyResults = requiredLazyPages.map((page) => {
  const item = manifest[page];
  return {
    page,
    isDynamicEntry: Boolean(item?.isDynamicEntry),
    file: item?.file ?? null,
    inInitialStaticGraph: staticImports.has(page),
  };
});

const failures = lazyResults.filter((item) => !item.isDynamicEntry || item.inInitialStaticGraph);
if (failures.length > 0) {
  console.error(JSON.stringify({ failures, lazyResults }, null, 2));
  throw new Error('Secondary Mini App routes must be dynamic entries outside the initial static graph.');
}

const importCycles = findSourceImportCycles(srcDir);
if (importCycles.length > 0) {
  console.error(JSON.stringify({ importCycles }, null, 2));
  throw new Error('Mini App source imports must not contain cycles.');
}

const assetsDir = path.join(root, 'dist', 'assets');
const files = fs.readdirSync(assetsDir)
  .map((name) => {
    const filePath = path.join(assetsDir, name);
    const content = fs.readFileSync(filePath);
    const extension = path.extname(name).slice(1) || 'file';
    return {
      name: `assets/${name}`,
      type: extension,
      sizeBytes: content.length,
      gzipBytes: zlib.gzipSync(content).length,
    };
  })
  .sort((left, right) => left.name.localeCompare(right.name));

const report = {
  entryKey: mainEntryKey,
  entryFile: mainEntry.file,
  entryCss: mainEntry.css ?? [],
  lazyRoutes: lazyResults,
  importCycles,
  totals: {
    jsBytes: files.filter((file) => file.type === 'js').reduce((sum, file) => sum + file.sizeBytes, 0),
    cssBytes: files.filter((file) => file.type === 'css').reduce((sum, file) => sum + file.sizeBytes, 0),
    jsGzipBytes: files.filter((file) => file.type === 'js').reduce((sum, file) => sum + file.gzipBytes, 0),
    cssGzipBytes: files.filter((file) => file.type === 'css').reduce((sum, file) => sum + file.gzipBytes, 0),
  },
  files,
};

console.log(JSON.stringify(report, null, 2));

function findSourceImportCycles(sourceDir) {
  const graph = buildImportGraph(sourceDir);
  const visited = new Set();
  const active = new Set();
  const stack = [];
  const cycles = [];
  const seenCycleKeys = new Set();

  for (const file of graph.keys()) {
    visit(file);
  }

  return cycles;

  function visit(file) {
    if (active.has(file)) {
      const cycleStart = stack.indexOf(file);
      if (cycleStart < 0) {
        return;
      }
      const cycle = [...stack.slice(cycleStart), file].map(toSourcePath);
      const key = canonicalCycleKey(cycle);
      if (!seenCycleKeys.has(key)) {
        seenCycleKeys.add(key);
        cycles.push(cycle);
      }
      return;
    }
    if (visited.has(file)) {
      return;
    }

    visited.add(file);
    active.add(file);
    stack.push(file);
    for (const dependency of graph.get(file) ?? []) {
      visit(dependency);
    }
    stack.pop();
    active.delete(file);
  }
}

function buildImportGraph(sourceDir) {
  const sourceFiles = listSourceFiles(sourceDir);
  const sourceFileSet = new Set(sourceFiles);
  const graph = new Map(sourceFiles.map((file) => [file, []]));

  for (const file of sourceFiles) {
    const content = fs.readFileSync(file, 'utf8');
    for (const specifier of findRelativeImportSpecifiers(content)) {
      const dependency = resolveSourceImport(file, specifier, sourceFileSet);
      if (dependency) {
        graph.get(file).push(dependency);
      }
    }
  }

  return graph;
}

function listSourceFiles(directory) {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...listSourceFiles(entryPath));
      continue;
    }
    if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      files.push(entryPath);
    }
  }
  return files;
}

function findRelativeImportSpecifiers(content) {
  const specifiers = [];
  const importPattern =
    /import\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]|export\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g;
  for (const match of content.matchAll(importPattern)) {
    const specifier = match[1] ?? match[2] ?? match[3];
    if (specifier?.startsWith('.')) {
      specifiers.push(specifier);
    }
  }
  return specifiers;
}

function resolveSourceImport(importer, specifier, sourceFileSet) {
  const base = path.resolve(path.dirname(importer), specifier);
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    path.join(base, 'index.ts'),
    path.join(base, 'index.tsx'),
  ];
  return candidates.find((candidate) => sourceFileSet.has(candidate)) ?? null;
}

function toSourcePath(file) {
  return path.relative(root, file).split(path.sep).join('/');
}

function canonicalCycleKey(cycle) {
  const nodes = cycle.slice(0, -1);
  const rotations = nodes.map((_, index) => [
    ...nodes.slice(index),
    ...nodes.slice(0, index),
  ].join('>'));
  return rotations.sort()[0];
}
