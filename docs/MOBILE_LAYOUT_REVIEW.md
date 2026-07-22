# Hermes Control Android Mobile Layout and Usability Review

Date: 2026-07-22

## 1. Environment and method

- Device category: physical Android phone, Samsung SM-S938U class device.
- Android: 16, API 36.
- Display: 1080 x 2340 physical pixels; effective density override 420 dpi; portrait orientation.
- Installed app package/version: `com.anonymous.hermesmobilecontrol`, version 0.1.0, version code 1.
- The installed APK was compared with the repository checkout. The checkout was fast-forwarded to the current `origin/main` before source comparison because the initially checked-out revision predated the installed app's Inbox/Activity/More navigation.
- Evidence sources: live Android UIAutomator XML hierarchy, device taps/navigation, bounds/state/clickability/content descriptions, non-image device diagnostics, and React Native/Expo source inspection.
- No screenshots, image capture, OCR, vision/image-analysis tools, image URLs, base64 images, or image generation were used.
- No app code, server state, credentials, task records, project records, or device data were modified. No task was submitted. The only temporary files created were local UI hierarchy XML dumps; they were removed after inspection.

## 2. Screens reviewed

Live device review:

- Initial launch / Inbox dashboard and fixed bottom navigation.
- Projects list with populated project cards.
- Project detail for an existing workspace.
- New Task, including prompt field, templates, expanded Task options, project chips, and disabled submit state.
- Activity/Tasks list with search, horizontal filters, populated task cards, and fixed bottom navigation.
- Task Detail for a blocked task, including retry/continuation/archive actions, attempt timeline, blocker message, and expandable context/error sections.
- More screen and its Diagnostics, Recovery Plan, and Settings entry points.
- Settings connection form, connection state, WebSocket state, and expanded Diagnostics section.

Source-only or not conclusively exercised live:

- Needs Attention route as a standalone screen.
- Project management/create/adopt/clone flows.
- Recovery Plan populated/apply confirmation flow.
- Actual keyboard-open submission and lower-control behavior.
- Voice permission/transcription flow.
- Offline queue creation/retry/discard reconciliation.
- Approval decision submission.

## 3. Findings

### M-01 — Fixed bottom navigation intercepts New Task project controls

- Severity: High
- Screen/path: New Task -> Task options -> Project selection.
- Direct evidence: the live hierarchy placed project controls `new-task-project-hermes-control-2` and `new-task-project-infra-fabric` at y=2120..2218. The fixed bottom navigation occupied y=2018..2143. Their vertical ranges overlap by 23 pixels. The navigation item bounds were Inbox y=2018..2143, Projects y=2018..2143, New y=2018..2143, Activity y=2018..2143, and More y=2018..2143. A tap at x=500, y=2170, within the visible project-chip row but also within the fixed navigation's effective region, did not change the selected project; the screen hierarchy remained unchanged. A tap at x=200, y=2130 selected the Inbox navigation item.
- Relevant source: `apps/mobile/app/new-task.tsx:180-242` renders a single ScrollView with bottom padding; `apps/mobile/src/navigation/BottomNavigation.tsx:20-43` renders the navigator absolutely; `apps/mobile/src/navigation/constants.ts:1` defines an 84 px bar.
- User impact: project selection can be impossible or can navigate away when the user taps a lower project chip. This is especially serious because project context determines where a task runs.
- Recommended fix: guarantee that the ScrollView's effective content and hit targets end above the complete navigation shell, including shell top padding and safe-area behavior. Prefer a shared bottom-inset/content-padding constant derived from the actual rendered navigator height, and verify every lower control after scrolling on a physical device. Do not rely only on a nominal 84 px value.
- Confidence: High; live bounds and a physical tap reproduced the conflict.
- Non-image limitation: exact visual layering/z-order is inferred from hierarchy bounds and interaction result, not from pixels.

### M-02 — Projects list content is reachable inside the bottom navigation bounds

- Severity: High
- Screen/path: Projects list after scrolling toward the third project card.
- Direct evidence: the live hierarchy showed the third project card at y=1875..2340, while the fixed bottom navigation occupied y=2018..2143. The card therefore extends through the full navigation area. Its metadata rows included visible content in that interval, including `WORKSPACE`, the workspace path, and `REPOSITORY`.
- Relevant source: `apps/mobile/app/projects/index.tsx:32` uses bottom padding `insets.bottom + bottomNavigationHeight + spacing.xl`, while `apps/mobile/src/navigation/BottomNavigation.tsx:94-100` places the bar at the bottom absolutely.
- User impact: lower project metadata can be obscured or taps can be captured by navigation. The issue is more likely with long lists and large cards than on the first viewport.
- Recommended fix: reserve the full measured fixed-navigation footprint in all root ScrollViews, and test at the end of populated lists. Consider rendering the navigation outside the content's hit-test region or using a layout container that naturally allocates space instead of absolute overlay positioning.
- Confidence: High for geometric overlap; Medium for which exact child elements are visually hidden because no imagery was used.

### M-03 — Inbox section header overlaps the fixed navigation area

- Severity: Medium
- Screen/path: Inbox dashboard at the captured populated state.
- Direct evidence: the live hierarchy placed the `Recent work` section header at y=1920..2035. The fixed bottom navigation begins at y=2018, producing a 17 px overlap. The bottom-navigation items were simultaneously exposed in y=2018..2143.
- Relevant source: `apps/mobile/app/index.tsx:23` uses the same bottom-padding formula, while the navigation is absolutely positioned in `src/navigation/BottomNavigation.tsx:94-100`.
- User impact: the Recent work heading/action region can be partially obscured or have ambiguous touch ownership even before the user reaches the end of the list.
- Recommended fix: use a single layout-level safe-area/inset calculation that includes the actual bar height, shell padding, and any platform gesture area. Verify section headers and action links, not only the final list row.
- Confidence: High for bound overlap; Medium for visual severity without imagery.

### M-04 — Settings presents contradictory WebSocket state

- Severity: Medium
- Screen/path: More -> Settings -> Connection state.
- Direct evidence: the live hierarchy simultaneously exposed `WEBSOCKET` = `connected` and `Closed · 1006 · Software caused connection abort`. The displayed endpoint was redacted by the app as `ws://.../ws/events?token=[REDACTED]`, so no credential was exposed in this report.
- Relevant source: `apps/mobile/src/state/data-store.ts:93-105` sets the current WebSocket state on open/close; `apps/mobile/app/settings.tsx:54-63` always renders the retained close code/reason whenever `websocketCloseCode !== null`, even when the current state is connected.
- User impact: users cannot tell whether the connection is healthy or currently failed. This can lead to unnecessary recovery actions or distrust of current task data.
- Recommended fix: clear close code/reason when a new connection opens, or render historical close information under an explicitly labeled `Last disconnect` row separate from current state. Also distinguish current connection state from historical reconnect diagnostics.
- Confidence: High; contradictory text was directly observed and the source path explains it.

### M-05 — Bottom navigation accessibility semantics are incomplete

- Severity: Medium
- Screen/path: all root screens with the fixed bottom navigation.
- Direct evidence: the live hierarchy exposed each navigation item as clickable with content descriptions such as `\uf184, Inbox`, `\uf170, Projects`, and `\uf191, Activity`; the icon glyph is included in the accessible description rather than a clean semantic label. No selected state was exposed for the active item in the observed hierarchy. By contrast, several newer controls in New Task explicitly use `accessibilityRole="button"` and `accessibilityState={{ selected: ... }}`.
- Relevant source: `apps/mobile/src/navigation/BottomNavigation.tsx:27-35` gives the Pressable a testID but no `accessibilityRole`, `accessibilityLabel`, or `accessibilityState`; the active state is represented only by styles at line 30.
- User impact: TalkBack users may hear implementation glyphs, and may not be told which destination is selected. This makes navigation less understandable without relying on color/background styling.
- Recommended fix: set `accessibilityRole="tab"` or button semantics appropriate to the navigation model, provide a plain label, and expose `accessibilityState={{ selected: active }}`. Add an explicit badge announcement for unread attention if the badge is restored.
- Confidence: High; hierarchy metadata and source are direct evidence.

### M-06 — Unread attention badge is unreachable in the current navigation model

- Severity: Low
- Screen/path: fixed bottom navigation / Needs Attention discoverability.
- Direct evidence: the live Inbox showed `Needs attention` count 8 and the source data store reported unread attention state. However, the bottom navigation items are Inbox, Projects, New, Activity, and More. The badge condition in `BottomNavigation.tsx:35` is `item.label === 'Attention'`, but no current item has label `Attention`, so that branch cannot render.
- Relevant source: `apps/mobile/src/navigation/items.ts:8-13` and `apps/mobile/src/navigation/BottomNavigation.tsx:15,35`.
- User impact: unread attention may not be signaled in persistent navigation; users must discover it through the Inbox content or enter the Activity/More flows.
- Recommended fix: either remove the dead badge branch and intentionally place the unread indicator on Inbox/Activity, or add a clearly named Attention destination. Add a test that asserts the chosen badge destination and label remain aligned.
- Confidence: High; this is a direct source inconsistency. The visual absence was not judged from pixels.

### M-07 — Duplicate project identities are not distinguishable in task/project selection

- Severity: Medium
- Screen/path: Projects list and New Task -> Task options -> Project.
- Direct evidence: the live Projects hierarchy showed two separate cards with the visible name `hermes-control` and the same visible workspace path (redacted here); their only distinction in the hierarchy was internal test IDs ending in `hermes-control` and `hermes-control-2`. The New Task hierarchy likewise showed two selectable project buttons both labeled `hermes-control`.
- Relevant source: `apps/mobile/app/projects/index.tsx:43-46` renders `project.name` and metadata; `apps/mobile/app/new-task.tsx:238-242` renders `project.name` as the project-chip text while using project ID only as a testID.
- User impact: selecting or opening the wrong project is easy, and the selected context can be mistaken even though task execution is project-scoped.
- Recommended fix: show a disambiguating project ID/slug or a shortened unique folder suffix when names collide. In New Task, make the selected project label include a unique identifier and keep the selected state exposed semantically.
- Confidence: High; duplicate visible values were directly observed.

### M-08 — Long technical paths and metadata are not robustly represented

- Severity: Low
- Screen/path: Projects list, Project detail, Settings connection state, and task metadata.
- Direct evidence: source uses right-aligned `MetadataRow` values with `numberOfLines={1}` at `apps/mobile/src/components/MetadataRow.tsx:10-12`, and project cards render paths through that component. Project detail renders folder paths as regular single Text nodes (`app/projects/[projectId].tsx:84-90`) without a documented truncation/expansion affordance. The live hierarchy already showed long endpoint/path values consuming nearly the full available width.
- User impact: long workspace paths, project IDs, endpoint strings, and error text can become truncated or difficult to scan, reducing confidence about the active project context.
- Recommended fix: use a deliberate truncation policy with accessible full-value text, allow horizontal selection/copy for paths, and put high-value identity (project name + unique ID) before technical metadata. Validate with long fixture names and Windows/Unix paths.
- Confidence: Medium; source establishes the truncation risk, while exact clipping depends on font metrics and data.

## 4. Strengths

- The root dashboard clearly separates Needs attention, Active work, Recent work, and Projects. Live hierarchy bounds showed each section and its count/action region as distinct, semantically named content.
- Task Detail correctly omits the fixed bottom navigation on nested routes. The live hierarchy showed a normal back control and no bottom-nav nodes, reducing obstruction on the dense timeline/detail surface.
- New Task exposes a semantic accessibility label and hint for the instruction field (`Task instruction`, `Describe the work Hermes should perform`). Priority and project controls expose selected state in source, and the Task options disclosure exposed `Task options, −` in the live hierarchy.
- The New Task submit control was correctly disabled when the prompt was empty in the live hierarchy (`enabled=false`), preventing an empty submission.
- Task Detail presented consequential actions with explicit labels such as `Retry unchanged`, `Edit and retry`, `Continue session`, and `Remove from inbox`; blocked work also surfaced `Hermes needs attention` and a blocker message.
- Settings masked the token in the live hierarchy and displayed a redacted WebSocket endpoint, avoiding credential disclosure through the accessibility tree.
- Refreshable lists and offline/stale messaging are present in source for Inbox, Attention, Projects, Activity, and Recovery Plan. These states are structurally represented rather than relying solely on a spinner.
- The fixed bottom navigation slots were evenly distributed across the 1080 px width in the live hierarchy, with five consistently sized slots and centered icon/label stacks.

## 5. Prioritized recommendations

### Must-fix defects

1. Eliminate fixed bottom-navigation hit-test/content overlap across New Task, Projects, Inbox, and every root ScrollView. Verify the actual last interactive child and lower project controls on the physical device.
2. Fix contradictory Settings connection state by separating current WebSocket state from historical close information.
3. Disambiguate duplicate project names/paths in both Projects and New Task selection.
4. Add explicit bottom-navigation accessibility semantics and selected state.

### Polish and future improvements

1. Repair or remove the dead `item.label === 'Attention'` badge condition and place unread attention signaling on a reachable destination.
2. Define accessible truncation/copy behavior for long project paths, IDs, URLs, prompts, and errors.
3. Add automated layout assertions for content-bottom clearance and a physical-device flow that scrolls each populated root screen to its end.
4. Add keyboard-open tests for New Task, Project Manage, and Settings, including controls near the system gesture area.
5. Exercise and document Attention, Recovery Plan, project creation/adoption/clone, offline queue, and voice flows on a disposable fixture before declaring full mobile usability coverage.

## 6. Verification limitations

- No images were captured or inspected, so pixel-level visual claims, exact color contrast, font rendering, shadows, and visual clipping cannot be conclusively evaluated.
- UI hierarchy bounds establish geometric overlap and accessibility exposure, but not every z-order/detail of rendering. The New Task overlap was additionally validated through a physical tap whose result remained unchanged while a navigation tap succeeded in the same shared region.
- The phone's secure lockscreen interrupted some exploratory attempts; after unlock, the primary flows were resumed. No credentials were entered or extracted.
- The standalone Needs Attention screen, project management flows, populated Recovery Plan, keyboard-open flows, voice input, approval submission, and offline queue retry/discard/reconciliation were reviewed in source but not conclusively exercised live.
- No task was submitted, retried, approved, rejected, archived, restored, or otherwise changed during this review.
