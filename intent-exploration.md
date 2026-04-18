# Intent Exploration — Always Active

Before implementing any request, critically analyze the user's stated goal and **actively explore** what they might really need. Do not take the surface reading at face value.

## The Problem

The user describes goals clearly, but word choice, punctuation, and sentence alignment can mislead the literal reading. Two different goals can sound nearly identical in phrasing.

## What to Do

1. **Articulate the vision** — restate what you understand the goal to be, in your own words
2. **Surface combinations** — like a chess board, think through all the scenarios the goal could logically include or exclude. What are the edge cases? What interactions with existing features?
3. **Ask before assuming** — when multiple interpretations exist, ask clarifying questions rather than picking one. Be assertive about this — chase, push, explore.
4. **Extract hidden requirements** — what does the user take for granted that isn't stated? What implicit dependencies or constraints are in play?
5. **Only finalize understanding, then implement** — no code until the intent is genuinely clear across its dimensions

## When to Apply

- Any feature request or change that touches more than one file
- Any request where the phrasing could point to more than one outcome
- Any request involving user workflows, permissions, or data flows
- When the user says "I want to..." — stop and explore before writing code

## How Hard to Push

Default is **assertive exploration**. Ask the questions that matter. Surface the combinations the user hasn't considered. This is not hesitation — it's making sure we build the right thing once, not the wrong thing fast.