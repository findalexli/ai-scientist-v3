"""
Create side-by-side comparison grids from generated examples.
Shows Direct vs Tool-Augmented vs NB2 for each prompt.
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGES_DIR = Path(__file__).parent / "images"
RESULTS_FILE = Path(__file__).parent / "results.json"
OUTPUT_DIR = Path(__file__).parent

def make_grid():
    results = json.loads(RESULTS_FILE.read_text())

    cell_w, cell_h = 512, 512
    label_h = 80
    header_h = 40
    conditions = ["direct_imagen4", "tool_aug_imagen4", "direct_qwen", "tool_aug_qwen", "nb2_native"]
    col_labels = ["Direct Imagen4", "Tool-Aug Imagen4", "Direct Qwen", "Tool-Aug Qwen", "NB2 Native"]

    # Filter to results that have at least 2 conditions
    valid = [r for r in results if len(r.get("conditions", {})) >= 2]
    if not valid:
        print("No valid results found")
        return

    n_rows = len(valid)
    n_cols = len(conditions)
    grid_w = n_cols * cell_w + 20  # margin
    grid_h = header_h + n_rows * (cell_h + label_h) + 20

    grid = Image.new("RGB", (grid_w, grid_h), "white")
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font = ImageFont.load_default()
        font_small = font

    # Column headers
    for j, label in enumerate(col_labels):
        x = j * cell_w + cell_w // 2
        draw.text((x, 10), label, fill="black", font=font, anchor="mt")

    for i, r in enumerate(valid):
        y_off = header_h + i * (cell_h + label_h)

        for j, cond in enumerate(conditions):
            x_off = j * cell_w
            cond_data = r.get("conditions", {}).get(cond, {})
            img_path = cond_data.get("image_path")

            if img_path and Path(img_path).exists():
                img = Image.open(img_path).resize((cell_w, cell_h), Image.LANCZOS)
                grid.paste(img, (x_off, y_off))

                # Score overlay
                scores = cond_data.get("scores", {})
                if scores and "grounded_accuracy" in scores:
                    avg = sum(v for k,v in scores.items() if k != "reasoning" and isinstance(v, (int,float))) / 4
                    score_text = f"avg={avg:.1f}"
                    draw.rectangle((x_off, y_off + cell_h - 25, x_off + 80, y_off + cell_h), fill="black")
                    draw.text((x_off + 5, y_off + cell_h - 22), score_text, fill="white", font=font_small)
            else:
                draw.rectangle((x_off, y_off, x_off + cell_w, y_off + cell_h), fill="#f0f0f0")
                draw.text((x_off + cell_w//2, y_off + cell_h//2), "N/A", fill="gray", font=font, anchor="mm")

        # Row label below images
        prompt_text = r["prompt"][:90] + ("..." if len(r["prompt"]) > 90 else "")
        category = r.get("category", "")
        draw.text((10, y_off + cell_h + 5), f"[{category}] {prompt_text}", fill="black", font=font_small)

        # Show enriched prompt snippet
        enriched = r.get("enriched_prompt", "")[:120]
        if enriched:
            draw.text((10, y_off + cell_h + 25), f"Enriched: {enriched}...", fill="#555555", font=font_small)

    out_path = OUTPUT_DIR / "comparison_grid.png"
    grid.save(out_path, quality=95)
    print(f"Saved comparison grid: {out_path}")
    print(f"  {n_rows} rows x {n_cols} columns = {grid_w}x{grid_h} pixels")


def make_per_example_cards():
    """Create individual comparison cards for each example."""
    results = json.loads(RESULTS_FILE.read_text())

    for r in results:
        conditions = r.get("conditions", {})
        images = {}
        for cond, data in conditions.items():
            path = data.get("image_path")
            if path and Path(path).exists():
                images[cond] = Image.open(path)

        if len(images) < 2:
            continue

        card_w = 512
        n = len(images)
        total_w = n * card_w + (n-1) * 10  # gap
        card_h = 512 + 120  # image + label

        card = Image.new("RGB", (total_w, card_h), "white")
        draw = ImageDraw.Draw(card)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except:
            font = ImageFont.load_default()
            font_small = font

        label_map = {"direct": "Direct", "tool_augmented": "Tool-Augmented", "nb2_native": "NB2 Native"}
        for j, (cond, img) in enumerate(images.items()):
            x = j * (card_w + 10)
            resized = img.resize((card_w, 512), Image.LANCZOS)
            card.paste(resized, (x, 0))

            # Label
            label = label_map.get(cond, cond)
            scores = conditions[cond].get("scores", {})
            if scores and isinstance(scores.get("grounded_accuracy"), (int, float)):
                avg = sum(v for k,v in scores.items() if k != "reasoning" and isinstance(v, (int,float))) / 4
                label += f" (avg={avg:.1f})"
            draw.text((x + 5, 515), label, fill="black", font=font)

            # Score detail
            if scores and "reasoning" in scores:
                reason = scores["reasoning"][:100]
                draw.text((x + 5, 535), reason, fill="#555", font=font_small)

        # Title
        out = OUTPUT_DIR / f"card_{r['id']}.png"
        card.save(out, quality=95)
        print(f"Saved: {out.name}")


if __name__ == "__main__":
    make_grid()
    make_per_example_cards()
