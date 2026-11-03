# Room character poses

These three new room poses were generated with the built-in `image_gen` tool on 2026-11-03, using `ui/public/pet/idle-poster.png` as an identity reference. They are adaptations, not original drawings supplied by the referenced artists.

Reference identity and existing animation: [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet), with the character design attribution retained in [pet/ATTRIBUTION.md](../pet/ATTRIBUTION.md). Design references: ZipZipPipe and 上善无形; related community artwork: 可以叫我云大人 / 雾雪. Retain the source attribution, noncommercial and share-alike conditions described in the existing pet asset notices. These are not official DeepSeek assets.

Files:

- `walk-atlas.png`: 2048 × 768 RGBA; four 512 × 768 gait frames.
- `sitting.png`: 1254 × 1254 RGBA; an actual seated three-quarter pose.
- `sleeping.png`: 1536 × 1024 RGBA; a naturally curled side-lying pose.

Original generated alpha is retained. No standing sprite is rotated into a sleeping pose. Runtime texture coordinates select the atlas frames; a horizontal mirror changes walking direction. File dimensions and checksums are in `manifest.json`.

Final prompt set, with `ui/public/pet/idle-poster.png` as the identity reference and transparent background enabled in all three built-in calls:

1. **Walk atlas:** One production-ready horizontal four-frame walk cycle facing right in gentle three-quarter view. Preserve the reference blue hair, cyan eyes, white lace maid headband, navy dress, white whale apron, blue whale tail and tiny shoes. Four equal 512 × 768 cells in 2048 × 768. Contact right, passing, contact left, passing opposite; actual alternating legs and arms, consistent registration and head size, feet at a common baseline, transparent padding. Crisp detailed line art, no labels, panels, floor, background, glow or props.
2. **Seated:** One high-resolution transparent whole-character cutout, viewed slightly above and behind the right shoulder, facing the unseen desk at upper left/rear. Proper bent seated hips, horizontal thighs, bent knees, dangling feet, forearms and hands forward as if typing. Preserve the exact character and outfit. No chair, desk, screen or keyboard: the three-dimensional room supplies these. Entire character and clean padding, detailed anime shading and dark outlines.
3. **Sleeping:** One high-resolution transparent cutout of the same character, naturally curled on her side with eyes closed and cheek on folded hands, legs and whale tail relaxed. Isometric view above and front right, head toward upper left and feet toward lower right. A newly drawn lying pose, not a rotated upright character. No bed, blanket, pillow, floor, letters or background; crisp outlines and clean alpha.
