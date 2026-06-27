/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

declare module 'node:fs' {
  export function readFileSync(path: string, encoding: string): string;
}
