/**
 * Setup for the opt-in live test (vitest.live.config.ts). Runs in Node so the real
 * WebSocket keeps Node's own Event classes, and adds a jsdom page for React to render into.
 */
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:5173/' })
const g = globalThis as unknown as Record<string, unknown>
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!(key in g)) g[key] = (dom.window as unknown as Record<string, unknown>)[key]
}
g.window = dom.window
g.document = dom.window.document
g.localStorage = dom.window.localStorage
g.IS_REACT_ACT_ENVIRONMENT = true

await import('@testing-library/jest-dom/vitest')
