/**
 * Shared Vitest setup (all envs): minimal browser APIs the test env lacks.
 *
 * - IntersectionObserver: motion's `whileInView` (the canonical `Reveal`)
 *   instantiates it on mount; jsdom has none, so any render would crash
 *   without this no-op stub. Children still render (opacity doesn't hide from
 *   Testing Library queries); animation completion is never asserted.
 */

class NoopIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = "";
  readonly scrollMargin: string = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

Object.defineProperty(globalThis, "IntersectionObserver", {
  value: NoopIntersectionObserver,
  writable: true,
  configurable: true,
});
