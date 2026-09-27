# Scientific Calculator (Base-100 Engine)

A desktop scientific calculator whose arithmetic is performed entirely by a
custom **base-100 arbitrary-precision engine written from scratch** -
including sin, cos, tan, their inverses, hyperbolic functions, ln, log, exp,
sqrt, powers, and factorial. Python's `math` module is never used for the
actual math (see `decimal100.py`'s header comment for the one documented
exception: a couple of spots use a cheap floating-point estimate purely to
pick a small integer during range reduction, e.g. "how many times should I
halve this angle" - all real arithmetic still runs through the base-100
engine).

## Features

- **Copy/paste-friendly display.** The expression line and the main result
  are real text fields (not plain labels) - select and copy with your
  mouse or Ctrl+C, and type or paste a number/expression directly into the
  expression field.
- **One expanded, adaptive main display.** No separate panel to open - the
  main display itself shows the full-precision result *and* its scientific
  notation together. Font size shrinks automatically as numbers get longer
  (from 40pt down to 11pt for something like `1000!`, a 2,568-digit
  number), and a scrollbar (built into the display) takes over if content
  still doesn't fit - you'll never lose access to the exact value.
- **Keyboard input.** The expression field accepts typing directly -
  digits, `+ - * / ^ % . ( ) !`, function names like `sin(`, all work as
  soon as you click into it (or just start typing - it has focus on
  launch). Press **Enter** to compute, **Escape** to clear everything.
- **Processing indicator + Cancel.** Calculations run on a background
  thread so the UI never freezes. While a calculation is running you'll
  see "Processing..." next to a **Cancel** button - useful for things like
  very large factorials, which can genuinely take a while since every
  digit of every multiplication runs through the base-100 engine. Cancelling
  cleanly aborts the in-progress computation (checked periodically inside
  the engine's hot loops) rather than killing the app.
- **Per-result timing**, shown once a calculation completes.

## Files

| File | What it does |
|---|---|
| `bignum100.py` | Arbitrary-precision **signed integer** arithmetic in base-100 (add, subtract, multiply, long division). The foundation everything else is built on. |
| `decimal100.py` | Fixed-point **decimal** numbers (30 significant digits) built on `bignum100`. Implements every transcendental function from scratch via Taylor series / Newton's method / range reduction. |
| `evaluator.py` | Tokenizer + recursive-descent parser that evaluates full expressions like `sin(30) + 5^2`, entirely through `decimal100`. |
| `app.py` | The CustomTkinter desktop UI: 4 tabs (Basic, Trigonometric, Logarithm, Constants & Memory), resizable window, per-result timing display. |

## Running it

```bash
pip install customtkinter
python app.py
```

That's it - no other dependencies. The window is resizable (drag any edge/corner);
minimum size is 860x560 so the button grid stays usable.

## Building a native .exe / app

This can't be produced from a Linux sandbox without internet access, so
you'll need to run this step yourself, **on the target operating system**,
with an internet connection (to install PyInstaller):

```bash
pip install customtkinter pyinstaller
pyinstaller --onefile --windowed --name "ScientificCalculator" app.py
```

The finished executable appears in a new `dist/` folder:
- **Windows:** `dist/ScientificCalculator.exe`
- **macOS:** `dist/ScientificCalculator` (or `.app` bundle with `--windowed`)
- **Linux:** `dist/ScientificCalculator`

Run PyInstaller on Windows to get a `.exe`, on macOS to get a Mac app, etc. -
PyInstaller packages for whichever OS it's run on, it doesn't cross-compile.

## A note on precision & speed

- Internal working precision is **30 significant decimal digits** (adjustable
  via the `SCALE` constant at the top of `decimal100.py`).
- Every function was verified against Python's `math` module to at least
  13 decimal places of agreement during development.
- The per-result timing shown under the display reflects real computation
  time through the base-100 engine - trig/log/exp functions (which run
  Taylor series with dozens of big-number multiplications per call) will
  visibly take longer than simple arithmetic, which is expected and part
  of the point of this build.

## Known limitations (be aware of these)

- `nth_root` for even roots of negative numbers is correctly rejected (no
  real result), same as any calculator.
- `tan`, `asin`, `acos`, `atanh` etc. correctly raise domain errors at their
  mathematical boundaries (e.g. `tan(90)` in degree mode, `asin(2)`).
- The UI was built and logic-tested via a mocked UI toolkit in the build
  environment (no display was available there) - all calculation logic,
  button wiring, memory, keyboard shortcuts, the background-thread
  Processing/Cancel flow, and error handling were exercised and verified
  end-to-end, but you will be the first to see it actually rendered on
  screen. If any visual/layout issue turns up, tell me what you see and
  I'll fix it.
