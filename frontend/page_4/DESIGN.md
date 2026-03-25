# Design System Specification: The Fluid Intelligence Framework

## 1. Overview & Creative North Star: "The Digital Curator"
The Creative North Star for this design system is **The Digital Curator**. Unlike standard productivity tools that feel like rigid spreadsheets, this system treats AI-driven data as an editorial experience. We are moving away from the "boxy" SaaS aesthetic toward a layout that feels like a high-end digital publication—spacious, authoritative, and frictionless.

By leveraging **intentional asymmetry** and **tonal depth**, we break the traditional grid. We use overlapping elements and varying typographic scales to guide the eye through complex AI transcription and data flows without overwhelming the user. The goal is a "Tech-Forward" atmosphere that feels automated yet deeply human and trustworthy.

---

## 2. Colors & Surface Philosophy
This system rejects the "boxed-in" look of legacy software. We utilize a sophisticated palette of cool-toned neutrals and vibrant AI-driven accents.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders for sectioning or layout containment. Boundaries must be defined solely through:
1.  **Background Color Shifts:** e.g., A `surface-container-low` section sitting on a `surface` background.
2.  **Subtle Tonal Transitions:** Using the spacing scale to create "negative borders" through whitespace.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers, like stacked sheets of frosted glass.
*   **Base:** `surface` (#f6fafe) – The canvas.
*   **Sectioning:** `surface-container-low` (#f0f4f8) – For sidebar backgrounds or secondary panels.
*   **Interaction Hubs:** `surface-container` (#eaeef2) – For main content areas.
*   **Prominence:** `surface-container-lowest` (#ffffff) – For the primary cards or focus elements to make them "pop" against the gray base.

### The "Glass & Gradient" Rule
To escape the "flat" look, use **Glassmorphism** for floating elements (modals, popovers). Use semi-transparent surface colors with a `backdrop-blur` of 12px–20px. 
*   **Signature Textures:** For primary CTAs or progress indicators, use a subtle linear gradient from `primary` (#0058be) to `primary_container` (#2170e4) at a 135° angle to add "visual soul."

---

## 3. Typography: The Editorial Edge
We use a dual-font strategy to balance technical precision with high-end aesthetics.

*   **Display & Headlines (Manrope):** Chosen for its geometric yet friendly curves. Use `display-lg` and `headline-md` with tight letter-spacing (-0.02em) to create an authoritative, "editorial" feel for AI insights and page titles.
*   **Body & UI (Inter):** The workhorse for technical data and transcription text. Inter provides maximum legibility at small scales. 
*   **Hierarchy as Brand:** Use `label-sm` in all-caps with 0.05em tracking for metadata or AI confidence scores. This creates a "tech-forward" distinction between human-readable content and machine-generated data.

---

## 4. Elevation & Depth
In this design system, depth is a function of light and layering, not structural scaffolding.

### The Layering Principle
Stack tiers to create natural lift. Place a `surface-container-lowest` card on a `surface-container-low` background. The contrast in hex codes provides all the separation needed.

### Ambient Shadows
Shadows should feel like natural ambient light, not digital artifacts.
*   **Specs:** Blur: 24px–40px | Opacity: 4%–8%.
*   **Color:** Use a tinted version of `on_surface` (a deep navy-gray) rather than pure black to keep the shadows "airy."

### The "Ghost Border" Fallback
If a border is required for accessibility (e.g., input fields), use a **Ghost Border**: `outline-variant` (#c2c6d6) at **20% opacity**. Never use 100% opaque borders.

---

## 5. Components

### Cards & Containers
*   **Rule:** Forbid the use of divider lines. 
*   **Style:** Use `surface-container-lowest` for the card body. Use `2.5` (0.5rem) or `3` (0.6rem) spacing to separate internal groups of content. Apply `xl` (0.75rem) roundedness for a modern, approachable feel.

### Buttons
*   **Primary:** Gradient fill (`primary` to `primary_container`). `full` (9999px) roundedness to signify "action" and "flow."
*   **Secondary:** No background, `outline-variant` at 20% opacity (Ghost Border). Use `primary` color for text.
*   **Tertiary/Logic:** Use `tertiary` (#6b38d4) for AI-specific actions (e.g., "Summarize" or "Transcribe") to distinguish them from standard navigation.

### Input Fields
*   **Styling:** Use `surface_container_low` as the background fill. On focus, transition to a `primary` ghost border (20% opacity) and a subtle `primary_fixed` shadow glow.

### AI Progress Bars
*   **Concept:** Avoid a solid block. Use a thin track in `surface-container-highest` with a glowing `tertiary` (Logic Purple) indicator that features a subtle pulse animation to represent "thinking."

### Split-Pane Layouts
*   **Execution:** Use `surface` for the navigation (Left), `surface-container-low` for the file list (Middle), and `surface-container-lowest` for the active workspace (Right). The shift in tone creates a clear flow from "Broad" to "Specific" without a single divider line.

---

## 6. Do's and Don'ts

### Do:
*   **Use Asymmetric Padding:** Allow for more breathing room at the top of a layout (`24` / 5.5rem) than the sides (`12` / 2.75rem) to create an editorial "header" feel.
*   **Embrace Whitespace:** If an element feels "cluttered," increase the spacing token rather than adding a border or line.
*   **Color as Status:** Use `tertiary` (Logic Purple) exclusively for AI/Machine processes to build a mental model of "Human vs. AI" workflows.

### Don't:
*   **Don't use pure black text:** Always use `on_surface` (#171c1f) for body text to maintain a premium, soft-contrast look.
*   **Don't use 1px Dividers:** Use background tone shifts or `1.5` spacing units of empty space to separate list items.
*   **Don't use standard "Drop Shadows":** Avoid high-opacity, tight shadows. They make the UI feel heavy and dated.