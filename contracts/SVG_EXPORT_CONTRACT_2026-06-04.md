# SVG Export Contract

**Module**: `frontend/src/pages/AnalyticDetailPage.tsx`
**Date**: 2026-06-04
**Status**: In force.

## Scope

The `downloadSvg()` function in the analytic detail page serializes
the rendered chart SVG to a downloadable `.svg` file. This contract
governs the `getBBox()` fallback chain so that exports produce usable
files even when the SVG is not fully rendered.

## Invariants

1. **Primary path: `getBBox()`.** When the SVG is rendered and
   `getBBox()` succeeds, the exported SVG's `viewBox`, `width`, and
   `height` are set from the bounding box plus 18 px padding.

2. **Fallback 1: `viewBox` attribute.** When `getBBox()` throws, the
   function reads the existing `viewBox` attribute from the source
   SVG. If it contains four valid finite numbers, those are used with
   padding.

3. **Fallback 2: `clientWidth`/`offsetWidth`.** When no `viewBox`
   exists, the function reads `svg.clientWidth || svg.offsetWidth`
   and `svg.clientHeight || svg.offsetHeight` for dimensions.

4. **Fallback 3: safe defaults.** If all dimension sources are zero
   or unavailable, hardcoded defaults of 920 × 430 are used.

5. **Never empty.** The exported SVG always has a `viewBox`, `width`,
   and `height` attribute. The catch block never leaves the clone
   without dimensions.

## Preconditions

- A `<svg>` element exists inside `#chart-frame`.
- The SVG may or may not be rendered (e.g., hidden tab, detached DOM).

## Postconditions

- The downloaded `.svg` file has valid `viewBox`, `width`, and
  `height` attributes.
- The file opens correctly in Inkscape, Illustrator, and browsers.

## Failure modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| Exported SVG has no `viewBox` | Empty catch block (pre-fix state) | Use the fallback chain |
| Exported SVG is 0×0 | `clientWidth` and `offsetWidth` both zero, no hardcoded default | Hardcoded 920×430 default added |
| `getBBox()` throws in Safari | SVG not rendered | Caught by try/catch, falls through to viewBox |

## Test coverage

Frontend unit tests are not in scope for the backend test suite.
The fallback logic is verified by manual testing and code review.

`backend/tests/test_quickfixes.py::test_t5_svg_fallback_logic` (static
analysis of the source file to verify the fallback chain exists).

## References

- [MDN: SVGElement.getBBox()](https://developer.mozilla.org/en-US/docs/Web/API/SVGGraphicsElement/getBBox)
