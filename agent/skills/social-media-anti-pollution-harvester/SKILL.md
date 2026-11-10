---
name: social-media-anti-pollution-harvester
description: Precision harvester for finding external guest appearances, keynote talks, and interviews across social platforms while filtering out aggregator spam and false positive clips.
---

# Social Media Anti-Pollution Harvester

Harvests high-value external appearances of creators/entrepreneurs across YouTube and Facebook without dataset pollution.

## Core Filtering Heuristics

1. **Negative Channel Filters**:
   - Explicitly excludes the creator's own primary channel (prevents re-scraping internal content).
   - Excludes viral clip aggregators and unauthorized repost channels.

2. **3-Tier Verification Matrix**:
   - **Tier 1 (Query Precision)**: Targeted search queries with operators (`"Creator Name" AND (interview OR podcast OR keynote OR keynote speaker)`).
   - **Tier 2 (Attribution Check)**: Verifies the title or description attributes the guest explicitly.
   - **Tier 3 (Speaker Duration)**: Filters out shorts/clips under 3 minutes where guest contribution is nominal.

3. **Output Structure**:
   - Saves clean transcript and guest catalog in structured CSV and Markdown.
