/** Minimal types for the part of jsdom used by src/test/live-setup.ts (no @types/jsdom installed). */
declare module 'jsdom' {
  export class JSDOM {
    constructor(html?: string, options?: { url?: string })
    readonly window: Window & typeof globalThis
  }
}
