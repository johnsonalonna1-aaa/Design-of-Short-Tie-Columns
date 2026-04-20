import math
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Tied Column Design App", layout="wide")

# ------------------------------------------------------------
# Styling
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .small-note {color: #666; font-size: 0.92rem;}
    .result-card {
        padding: 1rem 1.1rem;
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 14px;
        background: rgba(240,242,246,0.35);
        margin-bottom: 0.7rem;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-top: 0.3rem;
        margin-bottom: 0.35rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Data
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

PRESET_CASES = {
    "Custom": None,
    "11-7(a)": {
        "pu": 390.0,
        "mu": 220.0,
        "arrangement": "two_faces",
        "side": 18.0,
        "long_bar": "#9",
        "tie_bar": "#3",
        "rho_060": 0.020,
        "rho_075": 0.016,
    },
    "11-7(b)": {
        "pu": 710.0,
        "mu": 50.0,
        "arrangement": "four_faces",
        "side": 20.0,
        "long_bar": "#7",
        "tie_bar": "#3",
        "rho_060": 0.010,
        "rho_075": 0.010,
    },
    "11-7(c)": {
        "pu": 200.0,
        "mu": 240.0,
        "arrangement": "four_faces",
        "side": 18.0,
        "long_bar": "#8",
        "tie_bar": "#3",
        "rho_060": 0.028,
        "rho_075": 0.016,
    },
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
    return {"16db": limit1, "48dtie": limit2, "least_dimension": limit3, "s": s}


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
                        "db (in)": props["diameter"],
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        by=["As provided (in²)", "No. bars", "Bar size"]
    ).reset_index(drop=True)


def select_default_count(arrangement: str, bar: str, as_req: float) -> int:
    bar_area = BAR_DATA[bar]["area"]
    for n in COMMON_BAR_COUNTS[arrangement]:
        if n * bar_area >= as_req:
            return n
    return COMMON_BAR_COUNTS[arrangement][-1]


def arrangement_label(value: str) -> str:
    return "Bars in two faces" if value == "two_faces" else "Bars in four faces"


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------
st.title("Tied Column Design App")
st.caption("A cleaner homework-style calculator for short tied concrete columns.")

with st.expander("How to use this app", expanded=False):
    st.markdown(
        """
- Pick a preset if you want to test Homework 11-7 quickly.
- Or keep **Custom** and enter your own values.
- Enter your graph-read steel ratios from the **γ = 0.60** and **γ = 0.75** interaction diagrams.
- The app interpolates **ρg**, computes required steel area, suggests bars, designs ties, and gives splice length.
        """
    )

# ------------------------------------------------------------
# Sidebar inputs
# ------------------------------------------------------------
st.sidebar.header("Inputs")
case_name = st.sidebar.selectbox("Preset case", list(PRESET_CASES.keys()))
preset = PRESET_CASES[case_name]

pu_default = preset["pu"] if preset else 200.0
mu_default = preset["mu"] if preset else 240.0
arr_default = preset["arrangement"] if preset else "four_faces"
side_default = preset["side"] if preset else 18.0
long_bar_default = preset["long_bar"] if preset else "#8"
tie_bar_default = preset["tie_bar"] if preset else "#3"
rho_060_default = preset["rho_060"] if preset else 0.020
rho_075_default = preset["rho_075"] if preset else 0.016

pu = st.sidebar.number_input("Pu (kips)", min_value=1.0, value=float(pu_default), step=10.0)
mu = st.sidebar.number_input("Mu (kip-ft)", min_value=0.0, value=float(mu_default), step=10.0)
fc = st.sidebar.number_input("f'c (psi)", min_value=2500.0, value=4000.0, step=500.0)
fy = st.sidebar.number_input("fy (psi)", min_value=40000.0, value=60000.0, step=5000.0)
arrangement = st.sidebar.selectbox(
    "Bar arrangement",
    ["two_faces", "four_faces"],
    index=0 if arr_default == "two_faces" else 1,
    format_func=arrangement_label,
)
trial_rho = st.sidebar.number_input("Initial ρg", min_value=0.005, max_value=0.050, value=0.015, step=0.001, format="%.3f")
side = st.sidebar.number_input("Chosen square side h = b (in)", min_value=8.0, value=float(side_default), step=2.0)
cover = st.sidebar.number_input("Clear cover to outside of tie (in)", min_value=1.0, value=1.5, step=0.5)
long_bar = st.sidebar.selectbox("Selected longitudinal bar", list(BAR_DATA.keys()), index=list(BAR_DATA.keys()).index(long_bar_default))
tie_bar = st.sidebar.selectbox("Tie bar size", ["#3", "#4"], index=0 if tie_bar_default == "#3" else 1)

st.sidebar.markdown("---")
st.sidebar.subheader("Graph-read ρg values")
rho_060 = st.sidebar.number_input("ρg from γ = 0.60", min_value=0.0, max_value=0.100, value=float(rho_060_default), step=0.001, format="%.3f")
rho_075 = st.sidebar.number_input("ρg from γ = 0.75", min_value=0.0, max_value=0.100, value=float(rho_075_default), step=0.001, format="%.3f")

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
selected_count = select_default_count(arrangement, long_bar, as_req)
selected_bar_area = BAR_DATA[long_bar]["area"]
selected_bar_db = BAR_DATA[long_bar]["diameter"]
as_provided = selected_count * selected_bar_area
recommended_tie = tie_size_recommendation(long_bar)
tie_results = tie_spacing(long_bar, tie_bar, side)
face_count = bars_per_face(arrangement, selected_count)
spacing_check = face_clear_spacing(side, long_bar, tie_bar, cover, face_count)
extra_crosstie = spacing_check is not None and spacing_check["clear"] > 6.0
ld = development_length_tension(long_bar, fy, fc)
ls = splice_length_class_b(ld)

# ------------------------------------------------------------
# Top summary
# ------------------------------------------------------------
metric_cols = st.columns(4)
metric_cols[0].metric("Section", f"{int(side)} in × {int(side)} in")
metric_cols[1].metric("Interpolated ρg", f"{rho_interp:.4f}")
metric_cols[2].metric("Required As", f"{as_req:.3f} in²")
metric_cols[3].metric("e/h", f"{eh:.3f}")

st.markdown(
    f"<div class='small-note'>Arrangement: <b>{arrangement_label(arrangement)}</b> &nbsp; | &nbsp; Selected longitudinal bar: <b>{long_bar}</b> &nbsp; | &nbsp; Selected tie: <b>{tie_bar}</b></div>",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Tabs
# ------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["Results", "Step-by-step", "Bar + tie checks", "Notes"])

with tab1:
    c1, c2 = st.columns([1.05, 1])

    with c1:
        st.markdown("<div class='section-title'>Final recommendation</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
<div class='result-card'>
<b>Column:</b> {int(side)} in × {int(side)} in square tied column<br>
<b>Steel ratio:</b> ρg = {rho_interp:.4f}<br>
<b>Required steel area:</b> As = {as_req:.3f} in²<br>
<b>Provide:</b> {selected_count} {long_bar} bars → As = {as_provided:.3f} in²<br>
<b>Ties:</b> {tie_bar} @ {tie_results['s']:.2f} in o.c.<br>
<b>Cross-tie:</b> {'Required' if extra_crosstie else 'Not required'}<br>
<b>Development length:</b> ld = {ld:.2f} in<br>
<b>Splice length:</b> ls = {ls:.2f} in
</div>
            """,
            unsafe_allow_html=True,
        )

        if rho_interp < 0.01:
            st.warning("ρg is below 0.01. Minimum column steel may control.")
        elif rho_interp > 0.04:
            st.warning("ρg is above 0.04. A larger section may be more practical.")
        else:
            st.success("ρg is in a practical homework-design range.")

    with c2:
        st.markdown("<div class='section-title'>Quick values</div>", unsafe_allow_html=True)
        quick_df = pd.DataFrame(
            {
                "Item": [
                    "Estimated Ag from trial formula",
                    "Estimated square side",
                    "Chosen Ag",
                    "e (in)",
                    "γ",
                    "x = Mu/(Agh)",
                    "y = Pu/Ag",
                ],
                "Value": [
                    f"{ag_est:.2f} in²",
                    f"{side_est:.2f} in",
                    f"{ag:.2f} in²",
                    f"{e_in:.2f}",
                    f"{gamma:.3f}",
                    f"{x:.3f}",
                    f"{y:.3f}",
                ],
            }
        )
        st.dataframe(quick_df, use_container_width=True, hide_index=True)

with tab2:
    st.markdown("<div class='section-title'>Step-by-step calculations</div>", unsafe_allow_html=True)

    st.write("1) Trial tied-column area")
    st.latex(
        rf"A_g \ge \frac{{{pu:.1f}}}{{0.40({fc_ksi:.3f}+{fy_ksi:.1f}({trial_rho:.3f}))}} = {ag_est:.2f}\ \text{{in}}^2"
    )

    st.write("2) Estimated square side")
    st.latex(rf"h_{{est}}=\sqrt{{{ag_est:.2f}}}={side_est:.2f}\ \text{{in}}")

    st.write("3) Chosen practical section")
    st.latex(rf"h=b={side:.1f}\ \text{{in}}, \quad A_g={side:.1f}\times{side:.1f}={ag:.1f}\ \text{{in}}^2")

    st.write("4) Eccentricity")
    st.latex(rf"e=\frac{{{mu:.1f}}}{{{pu:.1f}}}\times 12={e_in:.2f}\ \text{{in}}")
    st.latex(rf"\frac{{e}}{{h}}=\frac{{{e_in:.2f}}}{{{side:.1f}}}={eh:.3f}")

    st.write("5) Gamma")
    st.latex(rf"\gamma=\frac{{{side:.1f}-5}}{{{side:.1f}}}={gamma:.3f}")

    st.write("6) Diagram coordinates")
    st.latex(rf"x=\frac{{{mu:.1f}\times 12}}{{{ag:.1f}\times {side:.1f}}}={x:.3f}")
    st.latex(rf"y=\frac{{{pu:.1f}}}{{{ag:.1f}}}={y:.3f}")

    st.write("7) Graph-read values")
    st.latex(rf"\rho_{{g,0.60}}={rho_060:.3f}, \qquad \rho_{{g,0.75}}={rho_075:.3f}")

    st.write("8) Interpolated steel ratio")
    st.latex(
        rf"\rho_g={rho_060:.3f}+({rho_075:.3f}-{rho_060:.3f})\frac{{{gamma:.3f}-0.60}}{{0.75-0.60}}={rho_interp:.4f}"
    )

    st.write("9) Required steel area")
    st.latex(rf"A_s={rho_interp:.4f}({ag:.1f})={as_req:.3f}\ \text{{in}}^2")

with tab3:
    left_check, right_check = st.columns(2)

    with left_check:
        st.markdown("<div class='section-title'>Bar options</div>", unsafe_allow_html=True)
        if options_df.empty:
            st.warning("No common option in the built-in list satisfies the required steel.")
        else:
            st.dataframe(options_df, use_container_width=True, hide_index=True)

        st.info(f"The app uses **{selected_count} {long_bar} bars** for detailing checks.")

        st.markdown("<div class='section-title'>Tie spacing</div>", unsafe_allow_html=True)
        st.latex(rf"16d_b=16({selected_bar_db:.3f})={tie_results['16db']:.2f}")
        st.latex(rf"48d_{{tie}}=48({BAR_DATA[tie_bar]['diameter']:.3f})={tie_results['48dtie']:.2f}")
        st.latex(
            rf"s=\min({tie_results['16db']:.2f},\ {tie_results['48dtie']:.2f},\ {tie_results['least_dimension']:.2f})={tie_results['s']:.2f}\ \text{{in}}"
        )

    with right_check:
        if spacing_check is not None:
            st.markdown("<div class='section-title'>Cross-tie check</div>", unsafe_allow_html=True)
            st.latex(
                rf"c={cover:.2f}+{BAR_DATA[tie_bar]['diameter']:.3f}+\frac{{{selected_bar_db:.3f}}}{{2}}={spacing_check['face_to_bar_center']:.3f}"
            )
            st.latex(
                rf"{side:.1f}-2({spacing_check['face_to_bar_center']:.3f})={spacing_check['outer_centers_span']:.3f}"
            )
            st.latex(
                rf"\frac{{{spacing_check['outer_centers_span']:.3f}}}{{{face_count-1}}}={spacing_check['ctc']:.3f}"
            )
            st.latex(
                rf"{spacing_check['ctc']:.3f}-{selected_bar_db:.3f}={spacing_check['clear']:.3f}"
            )

            if extra_crosstie:
                st.error("Clear spacing is greater than 6 in. Provide an additional cross-tie.")
            else:
                st.success("Clear spacing is 6 in. or less. No additional cross-tie is required.")

        st.markdown("<div class='section-title'>Development and splice length</div>", unsafe_allow_html=True)
        st.latex(rf"l_d={ld:.2f}\ \text{{in}}")
        st.latex(rf"l_s=1.3({ld:.2f})={ls:.2f}\ \text{{in}}")

with tab4:
    st.markdown("<div class='section-title'>Notes</div>", unsafe_allow_html=True)
    st.markdown(
        """
- This app is for study and homework support.
- The interaction-diagram step uses the graph-read values you enter.
- If your plotted point falls too far right on the interaction diagram, try a larger practical section and rerun the app.
- For homework 11-7, the presets make it faster to study each case.
        """
    )
