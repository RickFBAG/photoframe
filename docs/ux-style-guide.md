# Photoframe UX Style Guide

## Overview
This guide captures the visual language and interaction patterns that define the Photoframe experience. Use it as the shared reference for designers, engineers, and stakeholders when crafting new flows or refining existing ones.

## Color palette
- **Primary:** Midnight Navy (`#0C1B33`) for top-level navigation and emphasis elements.
- **Accent:** Sunrise Orange (`#FF7A45`) for key actions and status indicators.
- **Neutrals:** Mist (`#F2F4F7`) background with Slate (`#475467`) body text for high contrast and readability.

## Typography
- **Headings:** Inter, semi-bold, 28 px for H1 and 22 px for H2.
- **Body text:** Inter, regular, 16 px with 1.5 line height.
- **Caption:** Inter, medium, 14 px for supplementary details.

## Layout
- Maintain a 12-column responsive grid with 24 px gutters.
- Reserve the hero banner area for time-sensitive announcements or featured galleries.
- Use cards with 16 px internal padding to group related widgets.

## Screenshots & mockups
The legacy inline screenshot has been removed to keep the repository lightweight. Use the following description when aligning new UI work:

1. **Header** – Compact bar housing the Photoframe wordmark on the left and a contextual action button on the right.
2. **Primary widgets row** – Three equal-width cards summarizing photos, upcoming events, and weather. Each card uses the accent color for its headline.
3. **Activity feed** – A two-column section beneath the widgets containing recent uploads on the left and scheduled playlists on the right.
4. **Footer** – Minimal strip with system status and last sync timestamp.

For high-fidelity visuals, reference the "Photoframe Dashboard" project in the shared Figma workspace maintained by the design team. The prototypes there mirror the structure outlined above and are updated alongside every release.

## Accessibility considerations
- Maintain a minimum color contrast ratio of 4.5:1 for text and interactive elements.
- Provide text alternatives for all decorative imagery surfaced in the carousel.
- Ensure interactive controls are reachable via keyboard navigation and include focus outlines.

## Component library usage
Re-use the existing button, card, and modal components exported from the design system package. Any new component proposals should include rationale, visual specifications, and integration notes before development begins.
