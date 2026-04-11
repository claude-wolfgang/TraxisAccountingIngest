"""Core logic for renumbering CAM tools to match machine pocket assignments.

Given a machine's pocket map and a list of CAM tools, produces a renumbering
plan that assigns each tool its pocket number when possible, or the next
available pocket otherwise.
"""


def compute_renumbering(cam_tools, pocket_map):
    """Compute tool renumbering assignments.

    Args:
        cam_tools: list of dicts with keys:
            - tool_number: current T-number in the CAM setup
            - product_id: ProShop tool ID (matches pocket_map tool_number)
            - description: tool description for display
        pocket_map: dict from pocket_client.get_machine_pockets()
            {pocket_number: {"tool_number": str, "out_of_holder": float, "holder": str}}

    Returns:
        list of dicts:
            - tool_number_old: current T-number
            - tool_number_new: assigned pocket/T-number
            - product_id: ProShop tool ID
            - description: tool description
            - reason: why this assignment was made
    """
    # Build reverse map: proshop_tool_id → pocket_number
    tool_to_pocket = {}
    for pocket_num, info in pocket_map.items():
        tool_id = info.get("tool_number", "")
        if tool_id and tool_id not in tool_to_pocket:
            tool_to_pocket[tool_id] = pocket_num

    # Track which pocket numbers are already assigned in this plan
    used_pockets = set()
    assignments = []

    # First pass: assign tools that match pockets
    unmatched = []
    for tool in cam_tools:
        pid = (tool.get("product_id") or "").strip()
        if pid and pid in tool_to_pocket:
            new_num = tool_to_pocket[pid]
            used_pockets.add(new_num)
            assignments.append({
                "tool_number_old": tool["tool_number"],
                "tool_number_new": new_num,
                "product_id": pid,
                "description": tool.get("description", ""),
                "reason": f"Matched pocket #{new_num}",
            })
        else:
            unmatched.append(tool)

    # Collect all occupied pocket numbers (from machine + already assigned)
    all_occupied = set(pocket_map.keys()) | used_pockets

    # Second pass: assign unmatched tools to next available empty pockets
    # Start from pocket 1, skip occupied slots
    next_pocket = 1
    for tool in unmatched:
        while next_pocket in all_occupied:
            next_pocket += 1
        used_pockets.add(next_pocket)
        all_occupied.add(next_pocket)
        pid = (tool.get("product_id") or "").strip()
        assignments.append({
            "tool_number_old": tool["tool_number"],
            "tool_number_new": next_pocket,
            "product_id": pid,
            "description": tool.get("description", ""),
            "reason": "No pocket match — assigned empty pocket" if pid else "No Product ID — assigned empty pocket",
        })
        next_pocket += 1

    # Sort by new tool number for cleaner display
    assignments.sort(key=lambda a: a["tool_number_new"])
    return assignments


def format_preview(assignments):
    """Format assignments as a human-readable preview string."""
    lines = []
    lines.append(f"{'Old T#':>7}  {'New T#':>7}  {'Reason':<35}  Description")
    lines.append("-" * 90)
    for a in assignments:
        changed = " *" if a["tool_number_old"] != a["tool_number_new"] else "  "
        lines.append(
            f"  T{a['tool_number_old']:<5}  T{a['tool_number_new']:<5}{changed}"
            f"  {a['reason']:<35}  {a['description'][:40]}"
        )
    changed_count = sum(1 for a in assignments if a["tool_number_old"] != a["tool_number_new"])
    lines.append(f"\n{changed_count} of {len(assignments)} tools will be renumbered.")
    return "\n".join(lines)
