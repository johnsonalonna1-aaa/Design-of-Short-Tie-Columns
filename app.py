import math
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Tied Column Design App", layout="wide")

# ------------------------------------------------------------
# Bar data
# ------------------------------------------------------------
BAR_DATA: Dict[str, Dict[str, float]] = {
    "#3": {"diameter": 0.375, "area": 0.11},
    "#4": {"diameter": 0.500, "area": 0.20},
    "#5": {"diameter": 0.625, "area": 0.31},
    "#6": {"diameter": 0.750, "area": 0.44},
    "#7": {"diameter": 0.875, "area": 0.60},
    "#8": {"diameter": 1.000, "area": 0.79},
    "#9": {"diameter": 1.128, "area": 1.00},
    "#10": {"diameter": 1.270, "area": 1.27},
    "#11": {"diameter": 1.410, "area": 1.56},
}

# Homework-style preset graph-read values
# key = (arrangement, side_in, Pu, Mu)
PRESET_RHO_READS = {
    ("two_faces", 18.0, 390.0, 220.0): {"rho_060": 0.020, "rho_075": 0.016},
    ("four_faces", 20.0, 710.0, 50.0): {"rho_060": 0.010, "rho_075": 0.010},
    ("four_faces", 18.0, 200.0, 240.0): {"rho_060": 0.028, "rho_075": 0.016},
}

COMMON_BAR_COUNTS = {
    "two_faces": [4, 6, 8],
    "four_faces": [8, 12],
}


# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
def estimate_trial_area_tied(pu_kips: float, fc_ksi: float, fy_ksi: float, rho_g: float) -> float:
    return pu_kips / (0.40 * (fc_ksi + fy_ksi * rho_g))


def eccentricity_in(mu_kip_ft: float, pu_kips: float) -> float:
    return (mu_kip_ft / pu_kips) * 12.0


def gamma_value(side_in: float, d_prime_in: float = 2.5) -> float:
    return (side_in - 2.0 * d_prime_in) / side_in


def diagram_coordinates(pu_kips: float, mu_kip_ft: float, area_in2: float, side_in: float) -> Tuple[float, float]:
    x = (mu_kip_ft * 12.0) / (area_in2 * side_in)
    y = pu_kips / area_in2
    return x, y


def interpolate_rho(gamma_actual: float, rho_060: float, rho_075: float) -> float:
    return rho_060 + (rho_075 - rho_060) * ((gamma_actual - 0.60) / (0.75 - 0.60))


def preset_lookup(arrangement: str, side_in: float, pu_kips: float, mu_kip_ft: float) -> Optional[Dict[str, float]]:
    key = (arrangement, float(side_in), float(pu_kips), float(mu_kip_ft))
    return PRESET_RHO_READS.get(key)


def required_steel_area(rho_g: float, area_in2: float) -> float:
    return rho_g * area_in2


def tie_size_recommendation(long_bar: str) -> str:
    long_num = int(long_bar.replace("#", ""))
    return "#3" if long_num <= 10 else "#4"


def tie_spacing(long_bar: str, tie_bar: str, side_in: float) -> Dict[str, float]:
    db = BAR_DATA[long_bar]["diameter"]
    dtie = BAR_DATA[tie_bar]["diameter"]
    limit1 = 16.0 * db
    limit2 = 48.0 * dtie
    limit3 = side_in
    s = min(limit1, limit2, limit3)
    return {
        "16db": limit1,
        "48dtie": limit2,
        "least_dimension": limit3,
        "s": s,
    }


def bars_per_face(arrangement: str, n_bars: int) -> int:
    if arrangement == "two_faces":
        return n_bars // 2
    return 3 if n_bars == 8 else 4


def face_clear_spacing(
    side_in: float,
    long_bar: str,
    tie_bar: str,
    clear_cover_to_outside_tie_in: float,
    bars_on_face: int,
) -> Optional[Dict[str, float]]:
    if bars_on_face < 3:
        return None

    db = BAR_DATA[long_bar]["diameter"]
    dtie = BAR_DATA[tie_bar]["diameter"]

    face_to_bar_center = clear_cover_to_outside_tie_in + dtie + db / 2.0
    outer_centers_span = side_in - 2.0 * face_to_bar_center
    spaces = bars_on_face - 1
    ctc = outer_centers_span / spaces
    clear_spacing = ctc - db

    return {
        "face_to_bar_center": face_to_bar_center,
        "outer_centers_span": outer_centers_span,
        "ctc": ctc,
        "clear": clear_spacing,
    }


def development_length_tension(
    long_bar: str,
    fy_psi: float,
    fc_psi: float,
    lambda_concrete: float = 1.0,
    psi_t: float = 1.0,
    psi_e: float = 1.0,
    psi_g: float = 1.0,
) -> float:
    db = BAR_DATA[long_bar]["diameter"]
    bar_num = int(long_bar.replace("#", ""))
    denominator = 20.0 if bar_num >= 7 else 25.0
    return (fy_psi * psi_t * psi_e * psi_g / (denominator * lambda_concrete * math.sqrt(fc_psi))) * db


def splice_length_class_b(ld_in: float) -> float:
    return 1.3 * ld_in


def build_bar_options(arrangement: str, required_as: float) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    for bar, props in BAR_DATA.items():
        if bar in {"#3", "#4", "#5"}:
            continue
        for n_bars in COMMON_BAR_COUNTS[arrangement]:
            as_provided = n_bars * props["area"]
            if as_provided >= required_as:
                rows.append(
                    {
                        "Bar size": bar,
                        "No. bars": n_bars,
                        "As provided (in²)": round(as_provided, 3),
                        "Bar diameter db (in)": props["diameter"],
                    }
                )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        by=["As provided (in²)", "No. bars", "Bar size"]
    ).reset_index(drop=True)


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.title("Tied Column Design App")
st.caption("Homework-style Streamlit app for tied short-column design using interaction-diagram workflow.")

with st.expander("Methodology", expanded=False):
    st.markdown(
        """
1. Estimate trial tied-column area with  
   \\[
   A_g \\ge \\frac{P_u}{0.40(f'_c + f_y\\rho_g)}
   \\]
2. Choose a practical square section.
3. Compute eccentricity  
   \\[
   e = \\frac{M_u}{P_u}
   \\]
4. Compute  
   \\[
   \\gamma = \\frac{h - 2d'}{h}
   \\]
   using \\(d' \\approx 2.5\\,in\\).
5. Compute diagram coordinates  
   \\[
   x = \\frac{M_u}{A_g h}, \\qquad y = \\frac{P_u}{A_g}
   \\]
6. Enter graph-read \\(\\rho_g\\) values from the \\(\\gamma=0.60\\) and \\(\\gamma=0.75\\) charts.
7. Interpolate \\(\\rho_g\\), compute required \\(A_s\\), select bars, then design ties and splice lengths.
        """
    )

left, right = st.columns(2)

with left:
    st.subheader("Inputs")
    pu = st.number_input("Factored axial load Pu (kips)", min_value=1.0, value=200.0, step=10.0)
    mu = st.number_input("Factored moment Mu (kip-ft)", min_value=0.0, value=240.0, step=10.0)
    fc = st.number_input("Concrete strength f'c (psi)", min_value=2500.0, value=4000.0, step=500.0)
    fy = st.number_input("Steel yield strength fy (psi)", min_value=40000.0, value=60000.0, step=5000.0)
    arrangement = st.selectbox(
        "Bar arrangement",
        ["two_faces", "four_faces"],
        format_func=lambda x: "Bars in two faces" if x == "two_faces" else "Bars in four faces",
    )
    trial_rho = st.number_input("Initial trial ρg", min_value=0.005, max_value=0.050, value=0.015, step=0.001, format="%.3f")
    side = st.number_input("Chosen practical square side h = b (in)", min_value=8.0, value=18.0, step=2.0)

with right:
    st.subheader("Detailing + graph-read inputs")
    cover = st.number_input("Clear cover to outside of tie (in)", min_value=1.0, value=1.5, step=0.5)
    long_bar = st.selectbox("Selected longitudinal bar", list(BAR_DATA.keys()), index=6)
    recommended_tie = tie_size_recommendation(long_bar)
    tie_bar = st.selectbox("Tie bar size", ["#3", "#4"], index=0 if recommended_tie == "#3" else 1)

    preset = preset_lookup(arrangement, side, pu, mu)
    default_rho_060 = preset["rho_060"] if preset else 0.020
    default_rho_075 = preset["rho_075"] if preset else 0.016

    st.markdown("### Graph-read steel ratios")
    rho_060 = st.number_input("ρg from γ = 0.60 graph", min_value=0.0, max_value=0.100, value=float(default_rho_060), step=0.001, format="%.3f")
    rho_075 = st.number_input("ρg from γ = 0.75 graph", min_value=0.0, max_value=0.100, value=float(default_rho_075), step=0.001, format="%.3f")

# ------------------------------------------------------------
# Calculations
# ------------------------------------------------------------
fc_ksi = fc / 1000.0
fy_ksi = fy / 1000.0

ag_est = estimate_trial_area_tied(pu, fc_ksi, fy_ksi, trial_rho)
side_est = math.sqrt(ag_est)

ag = side ** 2
e_in = eccentricity_in(mu, pu)
eh = e_in / side
gamma = gamma_value(side)
x, y = diagram_coordinates(pu, mu, ag, side)
rho_interp = interpolate_rho(gamma, rho_060, rho_075)
as_req = required_steel_area(rho_interp, ag)

options_df = build_bar_options(arrangement, as_req)

selected_bar_area = BAR_DATA[long_bar]["area"]
selected_bar_db = BAR_DATA[long_bar]["diameter"]

selected_count = None
for n in COMMON_BAR_COUNTS[arrangement]:
    if n * selected_bar_area >= as_req:
        selected_count = n
        break
if selected_count is None:
    selected_count = COMMON_BAR_COUNTS[arrangement][-1]

as_provided = selected_count * selected_bar_area

tie_results = tie_spacing(long_bar, tie_bar, side)
face_count = bars_per_face(arrangement, selected_count)
spacing_check = face_clear_spacing(side, long_bar, tie_bar, cover, face_count)
extra_crosstie = spacing_check is not None and spacing_check["clear"] > 6.0

ld = development_length_tension(long_bar, fy, fc)
ls = splice_length_class_b(ld)

# ------------------------------------------------------------
# Output
# ------------------------------------------------------------
st.markdown("---")
st.subheader("Summary")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Estimated Ag", f"{ag_est:.1f} in²")
m2.metric("Estimated side", f"{side_est:.2f} in")
m3.metric("Chosen Ag", f"{ag:.1f} in²")
m4.metric("e/h", f"{eh:.3f}")

m5, m6, m7, m8 = st.columns(4)
m5.metric("γ", f"{gamma:.3f}")
m6.metric("x = Mu/(Agh)", f"{x:.3f}")
m7.metric("y = Pu/Ag", f"{y:.3f}")
m8.metric("Interpolated ρg", f"{rho_interp:.4f}")

st.markdown("### Detailed calculations")
st.markdown(
    f"""
- Trial tied-column area:
  \\[
  A_g \\ge \\frac{{P_u}}{{0.40(f'_c + f_y\\rho_g)}} =
  \\frac{{{pu:.1f}}}{{0.40({fc_ksi:.3f} + {fy_ksi:.1f} \\times {trial_rho:.3f})}} =
  {ag_est:.2f}\\;\\text{{in}}^2
  \\]

- Estimated square side:
  \\[
  h_{{est}} = \\sqrt{{A_g}} = \\sqrt{{{ag_est:.2f}}} = {side_est:.2f}\\;\\text{{in}}
  \\]

- Chosen practical section:
  \\[
  h=b={side:.1f}\\;\\text{{in}}, \\qquad A_g={side:.1f}\\times{side:.1f}={ag:.1f}\\;\\text{{in}}^2
  \\]

- Eccentricity:
  \\[
  e = \\frac{{M_u}}{{P_u}} = \\frac{{{mu:.1f}}}{{{pu:.1f}}}\\times 12 = {e_in:.2f}\\;\\text{{in}}
  \\]
  \\[
  \\frac{{e}}{{h}} = \\frac{{{e_in:.2f}}}{{{side:.1f}}} = {eh:.3f}
  \\]

- Gamma:
  \\[
  \\gamma = \\frac{{h - 2(2.5)}}{{h}} = \\frac{{{side:.1f} - 5}}{{{side:.1f}}} = {gamma:.3f}
  \\]

- Diagram coordinates:
  \\[
  x = \\frac{{M_u}}{{A_g h}} = \\frac{{{mu:.1f}\\times 12}}{{{ag:.1f}\\times {side:.1f}}} = {x:.3f}
  \\]
  \\[
  y = \\frac{{P_u}}{{A_g}} = \\frac{{{pu:.1f}}}{{{ag:.1f}}} = {y:.3f}
  \\]

- Graph-read values entered:
  \\[
  \\rho_{{g,0.60}} = {rho_060:.3f}, \\qquad \\rho_{{g,0.75}} = {rho_075:.3f}
  \\]

- Interpolation:
  \\[
  \\rho_g = \\rho_{{0.60}} + (\\rho_{{0.75}} - \\rho_{{0.60}})
  \\frac{{\\gamma - 0.60}}{{0.75 - 0.60}} = {rho_interp:.4f}
  \\]

- Required steel area:
  \\[
  A_s = \\rho_g A_g = {rho_interp:.4f}({ag:.1f}) = {as_req:.3f}\\;\\text{{in}}^2
  \\]
    """
)

st.markdown("### Bar options")
if options_df.empty:
    st.warning("No built-in common bar option satisfies the required steel. Try a larger section or larger bar size.")
else:
    st.dataframe(options_df, use_container_width=True)

st.markdown("### Selected bar for detailing checks")
st.write(f"Using **{selected_count} {long_bar} bars** gives **As = {as_provided:.3f} in²**.")

st.markdown("### Tie spacing")
st.markdown(
    f"""
- Recommended minimum tie size: **{recommended_tie}**
- User-selected tie size: **{tie_bar}**

\\[
16d_b = 16({selected_bar_db:.3f}) = {tie_results["16db"]:.2f}\\;\\text{{in}}
\\]

\\[
48d_{{tie}} = 48({BAR_DATA[tie_bar]["diameter"]:.3f}) = {tie_results["48dtie"]:.2f}\\;\\text{{in}}
\\]

\\[
\\text{{least dimension}} = {tie_results["least_dimension"]:.2f}\\;\\text{{in}}
\\]

\\[
s = \\min({tie_results["16db"]:.2f},\\ {tie_results["48dtie"]:.2f},\\ {tie_results["least_dimension"]:.2f})
= {tie_results["s"]:.2f}\\;\\text{{in}}
\\]
    """
)

if spacing_check is not None:
    st.markdown("### Cross-tie / unsupported-bar check")
    st.markdown(
        f"""
- Bars per face checked: **{face_count}**

Distance from face to bar center:
\\[
c = {cover:.2f} + {BAR_DATA[tie_bar]["diameter"]:.3f} + \\frac{{{selected_bar_db:.3f}}}{{2}}
= {spacing_check["face_to_bar_center"]:.3f}\\;\\text{{in}}
\\]

Outer supported bar center span:
\\[
{side:.1f} - 2({spacing_check["face_to_bar_center"]:.3f})
= {spacing_check["outer_centers_span"]:.3f}\\;\\text{{in}}
\\]

Center-to-center spacing:
\\[
\\frac{{{spacing_check["outer_centers_span"]:.3f}}}{{{face_count - 1}}}
= {spacing_check["ctc"]:.3f}\\;\\text{{in}}
\\]

Clear spacing:
\\[
{spacing_check["ctc"]:.3f} - {selected_bar_db:.3f}
= {spacing_check["clear"]:.3f}\\;\\text{{in}}
\\]
        """
    )

    if extra_crosstie:
        st.error("Clear spacing is greater than 6 in. Provide an additional cross-tie.")
    else:
        st.success("Clear spacing is 6 in. or less. No additional cross-tie is required.")

st.markdown("### Development and splice lengths")
st.markdown(
    f"""
For the selected bar:

\\[
\\ell_d = \\frac{{f_y\\psi_t\\psi_e\\psi_g}}{{20\\lambda\\sqrt{{f'_c}}}}d_b = {ld:.2f}\\;\\text{{in}}
\\]

Assuming Class B splice:

\\[
\\ell_s = 1.3\\ell_d = 1.3({ld:.2f}) = {ls:.2f}\\;\\text{{in}}
\\]
    """
)

st.markdown("### Final recommendation")
st.json(
    {
        "section": f"{side:.0f} in x {side:.0f} in square tied column",
        "rho_g": round(rho_interp, 4),
        "required_As_in2": round(as_req, 3),
        "provided_bars": f"{selected_count} {long_bar} bars",
        "provided_As_in2": round(as_provided, 3),
        "tie_design": f"{tie_bar} ties @ {tie_results['s']:.2f} in o.c.",
        "cross_tie": "Required" if extra_crosstie else "Not required",
        "ld_in": round(ld, 2),
        "ls_in": round(ls, 2),
    }
)

st.info("This app is for homework/study support. The interaction-diagram step uses graph-read values you enter, or built-in homework presets.")
