# OMR Template Specification: Calibrated 160-Question Standard Form

**Document Version:** 1.0  
**Target Form Identifier:** `OMR_AP_DSC_160_V1`  
**Calibrated Reference Image:** `OMR_325601.jpg` ($1644 \times 2272$ px, ~200 DPI)  

---

## 1. Sheet Geometry & Reference Coordinate Space

All coordinate measurements in this specification are normalized to the reference image canvas:
- **Reference Canvas Width ($W_{ref}$):** $1644$ pixels.
- **Reference Canvas Height ($H_{ref}$):** $2272$ pixels.
- **Coordinate Origin $(0, 0)$:** Top-left corner of the scanned document.

```
(0,0) +-------------------------------------------------------+ (1644, 0)
      | [Left Timing Track]               [Right Timing Track]|
      | (x=101..106, 49 marks)           (x=1496..1501, 49 m) |
      |                                                       |
      |   [Candidate Info Area: y=210..370]                   |
      |   - Hall Ticket (16 boxes): y=217..253, x=464..1091   |
      |   - Candidate Name:        y=255..305, x=464..1091    |
      |                                                       |
      |   [Question Bubble Grid: y=1076.5..2157.5]            |
      |   Col 1 (Q1..40)   Col 2 (Q41..80)   Col 3 (Q81..120) |
      |   x=274..376       x=628..730        x=982..1084      |
      |                                     Col 4 (Q121..160) |
      |                                     x=1336..1438      |
(0,2272)+-----------------------------------------------------+ (1644, 2272)
```

---

## 2. Geometric Alignment & Fiducial Timing Tracks

### 2.1 Dual Timing Track Specifications
The form includes two vertical timing tracks running down the left and right margins to enable affine alignment and skew cancellation.

| Attribute | Left Timing Track | Right Timing Track |
|---|---|---|
| **Total Marks Count** | Exactly 49 solid black rectangles | Exactly 49 solid black rectangles |
| **Horizontal Position ($x$)** | $101 \dots 106$ px | $1496 \dots 1501$ px |
| **Mark Width ($w$)** | $47 \dots 48$ px | $46 \dots 48$ px |
| **Mark Height ($h$)** | $18 \dots 20$ px | $17 \dots 19$ px |
| **First Mark ($y_{start}$)** | $y \approx 189$ px | $y \approx 212$ px |
| **Last Mark ($y_{end}$)** | $y \approx 2180$ px | $y \approx 2185$ px |
| **Average Vertical Pitch** | $\Delta y \approx 41.5$ px | $\Delta y \approx 41.5$ px |

### 2.2 Skew Detection & Affine Normalization Algorithm
1. Binarize the left margin strip ($x \in [70, 140]$) and right margin strip ($x \in [1460, 1530]$) using Otsu thresholding.
2. Filter contours matching the timing mark signature ($w \in [40, 55]$, $h \in [14, 26]$, $\text{aspect} \in [2.0, 3.2]$, $\text{area} > 550$).
3. Identify the centers of the first and last timing marks:
   - Top-left: $(x_{TL}, y_{TL})$
   - Bottom-left: $(x_{BL}, y_{BL})$
   - Top-right: $(x_{TR}, y_{TR})$
   - Bottom-right: $(x_{BR}, y_{BR})$
4. Calculate the rotational skew angle $\theta$:
   $$\theta = \arctan\left(\frac{y_{TR} - y_{TL}}{x_{TR} - x_{TL}}\right)$$
5. Apply an affine warp matrix to normalize the image to $0.00^\circ$ orientation and standard canvas scale prior to region extraction.

---

## 3. Optical Color Dropout Pipeline

The OMR sheet is printed with **red/orange dropout ink**, while student marks and handwriting are created using black/blue ballpoint pen or graphite pencil.

### 3.1 Color Space Transformation
When processing RGB channels $[B, G, R]$:
- Red ink has high reflectance in the Red channel: $R_{form} \approx 240 \dots 255$.
- White paper background has high reflectance in all channels: $R_{paper} \approx 235 \dots 250, G_{paper} \approx 220 \dots 235, B_{paper} \approx 220 \dots 235$.
- Graphite/black ink absorbs light across all spectra, especially in Red: $R_{ink} \approx 10 \dots 60$.

### 3.2 Inverted Red Channel Formula
To isolate candidate responses without interference from printed outlines:
$$I_{ink}(x, y) = 255 - R(x, y)$$

| Material / Region | Raw Red ($R$) | Inverted Red ($I_{ink}$) | Interpretation |
|---|:---:|:---:|---|
| Blank White Paper | $240 \dots 250$ | $5 \dots 15$ | Background noise (negligible) |
| Printed Red Bubble Outline | $235 \dots 245$ | $10 \dots 20$ | Dropped out (invisible) |
| Light Pencil Mark | $120 \dots 160$ | $95 \dots 135$ | Detectable mark |
| Fully Filled Bubble (Black Pen) | $15 \dots 50$ | $205 \dots 240$ | High-confidence marked response |

---

## 4. Candidate Identification Specifications

### 4.1 Hall Ticket Number Field
The Hall Ticket Number field consists of **16 horizontally segmented character boxes**.

| Parameter | Calibrated Value | Notes |
|---|:---:|---|
| **Field Bounding Box** | $y \in [217, 253]$, $x \in [464, 1091]$ | Total width = 627 px, height = 36 px |
| **Number of Character Boxes** | 16 boxes | Fixed length |
| **Box Pitch ($\Delta x$)** | $39.18$ pixels | Center-to-center distance |
| **Inner Box Crop Width** | 30 pixels | Excludes printed vertical boundary line |
| **Inner Box Crop Height** | 32 pixels | Excludes horizontal grid lines |
| **Expected Pattern** | `KNL2025SATS00001` | Format: `[A-Z]{3}\d{4}[A-Z]{4}\d{5}` |

#### 16-Box Coordinate Offsets (1x Image Space):
| Box # | X Start | X End | Y Start | Y End | Expected Char in Sample |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 464 | 496 | 217 | 253 | `K` |
| 2 | 503 | 535 | 217 | 253 | `N` |
| 3 | 542 | 574 | 217 | 253 | `L` |
| 4 | 581 | 613 | 217 | 253 | `2` |
| 5 | 620 | 652 | 217 | 253 | `0` |
| 6 | 659 | 691 | 217 | 253 | `2` |
| 7 | 699 | 731 | 217 | 253 | `5` |
| 8 | 738 | 770 | 217 | 253 | `S` |
| 9 | 777 | 809 | 217 | 253 | `A` |
| 10 | 816 | 848 | 217 | 253 | `T` |
| 11 | 855 | 887 | 217 | 253 | `S` |
| 12 | 894 | 926 | 217 | 253 | `0` |
| 13 | 934 | 966 | 217 | 253 | `0` |
| 14 | 973 | 1005 | 217 | 253 | `0` |
| 15 | 1012 | 1044 | 217 | 253 | `0` |
| 16 | 1051 | 1083 | 217 | 253 | `1` |

### 4.2 Candidate Name Field
- **Field Bounding Box:** $y \in [255, 305]$, $x \in [464, 1091]$.
- **Usage Policy:** When the Hall Ticket Number is absent or contains damaged boxes, the candidate name is used as the secondary identifier in accordance with the `KNL SA.xls` benchmark (e.g. `G SREENIVASULU`, `M KUMAR NAIK`).

---

## 5. Question Bubble Grid Layout & Coordinates

### 5.1 Column Groupings

| Column Group | Question Range | Origin Bubble A $(x, y)$ | Option B $(x)$ | Option C $(x)$ | Option D $(x)$ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **Column 1** | Q 1 to Q 40 | $(274.0, 1076.5)$ | $308.0$ | $342.0$ | $376.0$ |
| **Column 2** | Q 41 to Q 80 | $(628.0, 1076.5)$ | $662.0$ | $696.0$ | $730.0$ |
| **Column 3** | Q 81 to Q 120 | $(982.0, 1076.5)$ | $1016.0$ | $1050.0$ | $1084.0$ |
| **Column 4** | Q 121 to Q 160 | $(1336.0, 1076.5)$ | $1370.0$ | $1404.0$ | $1438.0$ |

- **Horizontal Bubble Pitch ($\Delta x_{opt}$):** Exactly $34.0$ pixels.
- **Inter-Column Pitch ($\Delta X_{col}$):** Exactly $354.0$ pixels ($628 - 274 = 354$, $982 - 628 = 354$, $1336 - 982 = 354$).
- **Vertical Row Pitch ($\Delta y_{row}$):** Exactly $27.7179$ pixels ($[2157.5 - 1076.5] / 39$).
- **Total Rows per Column:** 40 rows.

### 5.2 Bubble Sampling Geometry
For question $q \in [1, 160]$ and option index $k \in \{0: A, 1: B, 2: C, 3: D\}$:
$$\text{col\_idx} = \lfloor(q - 1) / 40\rfloor$$
$$\text{row\_idx} = (q - 1) \pmod{40}$$
$$x_{center}(q, k) = X_{base}[\text{col\_idx}] + k \cdot 34.0$$
$$y_{center}(q, k) = 1076.5 + \text{row\_idx} \cdot 27.7179 + \text{skew\_compensation}(x)$$

- **Sampling Radius ($R$):** $11$ pixels.
- **Core Mask Radius ($R_{core}$):** $8$ pixels ($75\%$ of outer radius).
- Sampling exclusively within the core mask eliminates edge artifacts from the printed circular bubble outline.

---

## 6. Bubble Classification & Fill Metrics

### 6.1 Multi-Signal Fill Extraction
For each option bubble $(q, k)$, calculate:
1. **Mean Inverted Core Density ($\mu_{core}$):**
   $$\mu_{core} = \frac{1}{|M_{core}|} \sum_{(x, y) \in M_{core}} I_{ink}(x, y)$$
2. **Surrounding Background Density ($\mu_{bg}$):**
   Calculated from an annular ring around the bubble ($R \in [12, 16]$ px).
3. **Contrast Signal ($\Delta_{fill}$):**
   $$\Delta_{fill} = \mu_{core} - \mu_{bg}$$

### 6.2 Decision Rules & Thresholds

| Classification | Condition | Action |
|---|---|---|
| **Single Marked Response** | $\max(\mu_{core}) \ge 60.0$ AND $\text{second\_max} < 55.0$ AND $\frac{\max}{\text{second\_max}} \ge 2.5$ | Confirmed marked option ($A, B, C, \text{ or } D$) |
| **Blank (Unattempted)** | $\max(\mu_{core}) < 45.0$ | Classified as `BLANK` |
| **Multiple Marked Options** | $\max(\mu_{core}) \ge 60.0$ AND $\text{second\_max} \ge 60.0$ | Classified as `MULTI` (scored 0, flagged for review) |
| **Ambiguous / Faint Mark** | $45.0 \le \max(\mu_{core}) < 60.0$ OR $1.4 \le \frac{\max}{\text{second\_max}} < 2.5$ | Classified as `AMBIGUOUS` (flagged for manual review) |

### 6.3 Confidence Score Calculation
For each question, a normalized confidence score $C \in [0.0, 1.0]$ is computed:
$$C = \min\left(1.0, \frac{\Delta_{fill}}{180.0} \times \left(1.0 - \frac{\text{second\_max}}{\max}\right)\right)$$
If $C < 0.65$, the question is automatically added to the operator's manual review queue.

