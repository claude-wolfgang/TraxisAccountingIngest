"""TPM WCS formatting: pure string logic for machinist-friendly descriptions."""

import logging

logger = logging.getLogger("tpm.wcs")


def format_for_machinist(origin_mode, box_point):
    """Translate Fusion WCS origin into machinist-friendly description.

    Standard output: "X: Center, Y: Near Side, Z: Top of Stock"

    For unusual modes (selected point, model origin, etc.) falls back
    to Fusion's own description since we can't decompose those.
    """
    if not origin_mode and not box_point:
        return None

    mode_lower = (origin_mode or '').lower()
    bp_lower = (box_point or '').lower()

    # For manual/unusual origins, can't decompose -- show raw Fusion text
    if any(kw in mode_lower for kw in ('selected', 'model origin')):
        parts = [p for p in (origin_mode, box_point) if p]
        return ', '.join(parts) if parts else None

    # Determine reference frame (stock vs part/model)
    is_stock = 'stock' in mode_lower

    # --- Z axis ---
    if 'top' in bp_lower:
        z_desc = 'Top of Stock' if is_stock else 'Top of Part'
    elif 'bottom' in bp_lower:
        z_desc = 'Bottom of Part' if not is_stock else 'Bottom of Stock'
    else:
        z_desc = 'Center'

    # --- X axis ---
    if 'left' in bp_lower:
        x_desc = 'Left'
    elif 'right' in bp_lower:
        x_desc = 'Right'
    else:
        x_desc = 'Center'

    # --- Y axis --- check both mode and box_point for front/back
    combined = mode_lower + ' ' + bp_lower
    if 'front' in combined or 'near' in combined:
        y_desc = 'Near Side'
    elif 'back' in combined or 'rear' in combined or 'far' in combined:
        y_desc = 'Far Side'
    else:
        y_desc = 'Center'

    return f"X: {x_desc}, Y: {y_desc}, Z: {z_desc}"
