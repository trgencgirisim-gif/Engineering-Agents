#!/usr/bin/env python3
"""
Enrich domain SKILL.md files with domain-specific methodology,
numerical sanity checks, expert differentiation, standards, and failure modes.

Usage:
    python scripts/enrich_skill_prompts.py          # dry-run (shows what would change)
    python scripts/enrich_skill_prompts.py --apply   # apply changes

Idempotent: safe to run multiple times. Skips files that already have
the "## Domain-Specific Methodology" section.
"""
import os
import sys
import glob

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "agents", "domain")

# ─── Content for 5 critical domains ─────────────────────────────────────

DOMAIN_ENRICHMENTS = {
    "yanma": {
        "a": """
## Domain-Specific Methodology

Decision tree for combustion analysis approach:
- **Premixed vs diffusion flames:** Damkohler number Da > 1 implies well-stirred reactor regime; Da < 1 implies flamelet regime
- **Mechanism selection:**
  - GRI-Mech 3.0: CH4/natural gas, T < 2500K, P < 10 atm
  - San Diego mechanism: H2, syngas, high-pressure applications (>10 atm)
  - JetSurF 2.0: kerosene/Jet-A surrogates, jet engine applications
  - USC Mech II: C1-C4 hydrocarbon species, broader range
- **Kinetics vs equilibrium:** If T > 1800K and lean conditions, detailed NOx kinetics required (thermal Zeldovich + prompt + N2O pathways). Equilibrium assumption acceptable for rich premixed below 1500K
- **Combustion regime:** Classify using Borghi diagram (Re_t vs Da): wrinkled flames, corrugated flames, thin reaction zones, broken reaction zones
- **Turbulence-chemistry interaction:** For turbulent flames, specify PDF/flamelet/EDC model and justify

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| CH4/air phi=1.0 T_ad | 2220-2240 K | >2400K = mechanism error |
| CH4/air phi=1.0 S_L | 36-40 cm/s | >60 cm/s = check mechanism |
| H2/air phi=1.0 T_ad | 2380-2400 K | >2600K = error |
| CO2 mass fraction (CH4 stoich) | 0.14-0.16 | >0.20 = mass balance error |
| NOx at phi=0.8 (dry) | 15-50 ppm | >200 ppm = check temperature |
| Ignition delay CH4 1atm 1200K | 1-10 ms | <0.01ms = error |
| Laminar burning velocity (any fuel) | 5-350 cm/s | >500 = check carefully |

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Chemical kinetics mechanisms and reaction pathway analysis
- Flame structure theory (premixed/diffusion/partially premixed)
- Damkohler number analysis and regime classification
- Rayleigh criterion for thermoacoustic instability
- Detonation vs deflagration transition theory
- Combustion instability analysis (Helmholtz modes, intrinsic flame instabilities)
- Detailed species transport and diffusion flame theory

## Standards & References

Mandatory references for combustion analysis:
- API 535 (Burner flame interaction), NFPA 86 (Ovens and furnaces)
- EN 746 (Industrial thermoprocessing equipment)
- ISO 13705 (Fired heaters for petroleum), ASME PTC 4.1 (Steam generators)
- EPA 40 CFR Part 60 (New Source Performance Standards — emissions)
- Turns, S.R., "An Introduction to Combustion" — standard textbook reference
- Glassman & Yetter, "Combustion" — advanced kinetics reference

## Failure Mode Awareness

Known limitations and edge cases:
- **Equilibrium assumption** invalid near extinction limits (phi < 0.5 or phi > 2.0)
- **GRI-Mech 3.0** inaccurate above 10 atm; use San Diego or detailed mechanisms
- **NOx prediction** unreliable without detailed kinetics at T > 1800K (thermal + prompt + N2O)
- **Laminar flame speed** correlations break down for highly preheated mixtures (T > 700K)
- **Soot modeling** requires PAH chemistry not in GRI-Mech 3.0
- **Radiative heat transfer** often neglected but critical in large furnaces (optical thickness > 1)
""",
        "b": """
## Domain-Specific Methodology

Practical combustion engineering approach:
- **Burner selection:** Match burner type to application — premixed for low-NOx, diffusion for stability, staged for ultra-low-NOx
- **Flame stability:** Calculate blowoff velocity (V_blowoff), flashback margin, turndown ratio. Use flame stability diagrams
- **Emissions compliance:** Determine applicable regulation (EPA, CARB, EU IED, ICAO) first, then design to meet limits with margin
- **Heat transfer:** Calculate radiative/convective split. For furnaces: use Hottel zone method or Monte Carlo
- **Efficiency:** Apply ASME PTC 4 methodology for boiler efficiency (direct/indirect method)

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Boiler efficiency (gas) | 80-95% | >98% = check losses |
| Excess air (gas burners) | 10-20% | <5% = CO risk, >30% = inefficient |
| NOx (gas turbine DLN) | 9-25 ppm @15% O2 | <5 ppm = verify measurement |
| Flame temperature (industrial) | 1500-2200 K | >2500K = check radiation |
| Turndown ratio | 3:1 to 10:1 | >20:1 = verify burner capability |
| Stack temperature | 120-200 C | >300C = heat recovery opportunity |

## Expert Differentiation

**Expert B (Applied) focus areas:**
- Burner design, selection, and commissioning
- Flame stability margins and operational envelope
- Emissions compliance (EPA, CARB, ICAO regulations)
- Industrial combustion systems (boilers, furnaces, gas turbines)
- Heat recovery and thermal efficiency optimization
- Flameholder geometry and recirculation zone design
- Practical flame monitoring and safety systems (UV/IR detectors, BMS)

## Standards & References

Industry standards for applied combustion:
- NFPA 85 (Boiler and Combustion Systems Hazards Code)
- NFPA 86 (Standard for Ovens and Furnaces)
- API 556 (Instrumentation, Control, and Protective Systems for Fired Heaters)
- ASME PTC 4 (Fired Steam Generators — performance test)
- EPA AP-42 (Emission Factors), 40 CFR 60/63
- ICAO Annex 16 Vol II (Aircraft engine emissions)

## Failure Mode Awareness

Practical failure modes to check:
- **Flashback risk** increases with hydrogen content >15% in fuel blend
- **Flame impingement** on tubes reduces life dramatically — check flame length vs chamber geometry
- **Low-NOx burners** may have higher CO at very low loads — check turndown performance
- **Fuel composition changes** (LNG vs pipeline gas) can cause detuning of premixed burners
- **Refractory damage** from flame impingement — check flame geometry at all loads
- **BMS (Burner Management System)** timing sequences critical for safety — verify purge times
"""
    },
    "yapisal": {
        "a": """
## Domain-Specific Methodology

Decision tree for structural analysis:
- **Linear vs nonlinear FEA:** Small deformations < 5% strain → linear elastic. Large deformation, plasticity, contact, buckling → geometric and/or material nonlinear
- **Fracture mechanics:** LEFM (K_IC approach) when plastic zone << crack length (small-scale yielding, plane strain). EPFM (J-integral, CTOD) for ductile materials or large-scale yielding
- **Fatigue life:** S-N curves for HCF (>10^4 cycles). Strain-life (Coffin-Manson) for LCF (<10^4 cycles). Miner's rule for variable amplitude loading
- **Buckling:** Euler formula for slender columns (slenderness ratio lambda > 100). Johnson formula for intermediate columns. Nonlinear buckling analysis for post-buckling behavior and imperfection sensitivity
- **Composite failure:** Tsai-Wu for general laminate failure prediction. Hashin criteria for damage initiation by mode. Puck criteria for inter-fiber failure in composites
- **Dynamic analysis:** Modal analysis for natural frequencies. Response spectrum for seismic. Time-history for impact/blast

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Steel yield (A36/S235) | 250 MPa | <100 MPa = wrong material |
| Steel E modulus | 200-210 GPa | <150 GPa = error |
| Aluminum E modulus | 68-72 GPa | >100 GPa = wrong material |
| Safety factor (static) | 1.5-4.0 | <1.0 = CRITICAL FAILURE |
| Poisson's ratio (steel) | 0.28-0.30 | >0.5 = incompressibility error |
| Max deflection/span ratio | L/250 to L/360 | >L/100 = serviceability failure |
| Natural frequency (building) | 0.5-5 Hz | <0.1 Hz = modeling error |
| Fatigue endurance limit (steel) | 0.35-0.50 * UTS | >0.7 * UTS = questionable |

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Continuum mechanics fundamentals (stress tensors, strain measures)
- Fracture mechanics theory (K_IC, J-integral, CTOD, crack growth laws)
- Finite element theory (element formulation, convergence, error estimation)
- Constitutive modeling (elastoplasticity, viscoelasticity, damage mechanics)
- Fatigue life prediction theory (crack initiation, propagation, Paris law)
- Stability theory (bifurcation, snap-through, limit point instability)
- Composite mechanics (CLT, first-ply failure, progressive damage)

## Standards & References

Mandatory structural engineering references:
- AISC 360 (Specification for Structural Steel Buildings)
- Eurocode 3 (EN 1993 — Design of Steel Structures)
- ACI 318 (Building Code for Structural Concrete)
- ASME BPVC Section VIII (Pressure Vessels)
- AWS D1.1 (Structural Welding Code — Steel)
- ASTM E399 (Plane-Strain Fracture Toughness Testing)
- ASTM E606 (Strain-Controlled Fatigue Testing)
- AISC Design Guide 1 (Column Base Plates)

## Failure Mode Awareness

Known limitations and edge cases:
- **Linear FEA** misses buckling modes — always run eigenvalue buckling check
- **Stress singularities** at sharp corners produce mesh-dependent results — use submodeling or fracture mechanics
- **Fatigue life** highly sensitive to surface finish, residual stress, and stress concentration factors
- **Composite failure theories** disagree significantly under biaxial loading — use multiple criteria
- **Connection stiffness** (semi-rigid) often idealized as pinned or fixed — can significantly affect frame behavior
- **P-delta effects** must be included for slender structures (amplification factor > 1.1)
""",
        "b": """
## Domain-Specific Methodology

Applied structural engineering approach:
- **Code-based design:** Start with applicable code (AISC, Eurocode, ACI). Determine load combinations (LRFD or ASD). Check all limit states
- **Connection design:** Design connections for actual forces. Check bolt shear/bearing, weld capacity, block shear, prying action
- **Construction sequence:** Consider erection loads, temporary bracing, concrete pour sequence, cambering
- **Inspection and NDT:** Specify inspection requirements (UT, MT, RT, VT) based on joint criticality
- **Practical safety factors:** Apply code-required safety factors. Add engineering judgment for uncertainties not covered by code

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Steel member weight | 15-100 kg/m2 (buildings) | >200 = check optimization |
| Rebar ratio (concrete) | 0.5-4% | <0.2% = below minimum |
| Bolt preload (A325) | 70% of UTS | <50% = insufficient |
| Weld size / plate thickness | 0.3-0.75 | >1.0 = check design |
| Foundation bearing pressure | 100-400 kPa (typical) | >600 = check soil capacity |
| Drift ratio (seismic) | 0.5-2.0% | >2.5% = code violation |

## Expert Differentiation

**Expert B (Applied) focus areas:**
- Code-based design (AISC, Eurocode, ACI — load combinations, limit states)
- Connection design (bolted, welded — shear, moment, bracing connections)
- Construction sequence analysis and temporary works
- Inspection and NDT requirements specification
- Practical safety factors and engineering judgment
- Weld design (fillet, CJP, PJP — prequalified procedures)
- Cost-effective structural optimization

## Standards & References

Industry standards for applied structural engineering:
- AISC 360 + AISC Manual of Steel Construction (14th/15th ed)
- ASCE 7 (Minimum Design Loads), IBC (International Building Code)
- ACI 318 (Concrete Code), ACI 301 (Specifications for Concrete)
- AISC 341 (Seismic Provisions), AISC 358 (Prequalified Connections)
- AWS D1.1 (Structural Welding — Steel), AWS D1.8 (Seismic Supplement)
- ASTM A992 (W shapes), ASTM A572 (HSS plates)

## Failure Mode Awareness

Practical failure modes to check:
- **Lateral-torsional buckling** of unbraced beams — check L_b vs L_p, L_r
- **Web crippling/buckling** under concentrated loads — check bearing stiffeners
- **Bolt slip** in slip-critical connections under service loads
- **Lamellar tearing** in thick plates with through-thickness tension
- **Fatigue at weld toes** — AISC Table A-3.1 fatigue categories
- **Corrosion allowance** for exposed steel — add thickness or specify coating system
"""
    },
    "kontrol": {
        "a": """
## Domain-Specific Methodology

Decision tree for control system analysis:
- **SISO vs MIMO:** SISO systems → classical methods (Bode, root locus, Nyquist). MIMO systems → state-space, singular value decomposition, decoupling
- **PID tuning:** Ziegler-Nichols (oscillation method) for initial tuning. Cohen-Coon (process reaction curve) for FOPDT models. IMC (Internal Model Control) for model-based tuning. SIMC (Skogestad) for simple, robust rules
- **Robust control:** Use H-infinity when plant uncertainty >20%. Mu-synthesis for structured uncertainty. Loop shaping for unstructured multiplicative uncertainty
- **Nonlinear systems:** Describing function for limit cycle prediction. Lyapunov methods for stability proof. Sliding mode control for robust tracking under model uncertainty
- **Digital control:** ZOH discretization for slow sampling (Ts > tau/10). Tustin (bilinear) for preserving frequency response shape. Matched pole-zero for critical dynamics

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Phase margin | 30-90 deg | <30 = fragile, <0 = unstable |
| Gain margin | 6-20 dB | <6 = fragile, <0 = unstable |
| Bandwidth | 2-10x crossover freq | >100 rad/s for mechanical = sensor noise issue |
| Settling time (2%) | 3-5 time constants | <1 tau = overly aggressive |
| Overshoot | 0-25% | >50% = underdamped, potential instability risk |
| Sampling rate | 10-20x bandwidth | <5x bandwidth = aliasing risk |
| Sensitivity peak Ms | 1.2-2.0 | >2.0 = robustness concern |

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Nyquist criterion rigorous application and encirclement counting
- Root locus rules (departure angles, breakaway points, asymptotic behavior)
- State-space controllability and observability analysis (PBH test, Kalman rank)
- Optimal control theory (LQR/LQG, Riccati equation, separation principle)
- H-infinity and mu-synthesis theory
- Nonlinear stability analysis (Lyapunov direct method, La Salle's invariance)
- Model reduction (balanced truncation, Hankel singular values)

## Standards & References

Control systems engineering references:
- ISA-5.1 (Instrumentation Symbols and Identification)
- IEC 61131-3 (Programmable Controllers — Programming Languages)
- IEC 61508 (Functional Safety — Safety Integrity Levels)
- DO-178C (Software Considerations in Airborne Systems)
- ISO 13849 (Safety of Machinery — Safety-Related Parts of Control Systems)
- Ogata, "Modern Control Engineering" — standard textbook
- Skogestad & Postlethwaite, "Multivariable Feedback Control" — MIMO reference

## Failure Mode Awareness

Known limitations and edge cases:
- **Bode/Nyquist** assume LTI — check linearization validity range
- **PID anti-windup** essential when actuator saturates — specify implementation
- **Sampling delay** adds phase lag of Ts/2 — include in continuous design margin
- **Sensor noise amplification** at high frequencies — check noise sensitivity function
- **Actuator rate limits** can cause limit cycles not predicted by linear analysis
- **Gain scheduling** linearization may miss transitions between operating points
""",
        "b": """
## Domain-Specific Methodology

Applied control systems engineering approach:
- **PID tuning in practice:** Use relay auto-tune for initial values. Fine-tune in simulation before commissioning. Always implement anti-windup (back-calculation or clamping)
- **Actuator sizing:** Verify actuator can handle required range, rate, and force/torque at all operating points
- **Sensor selection:** Match sensor bandwidth to control bandwidth with 10x margin. Check noise floor vs required resolution
- **Commissioning:** Step test to verify plant model. Tune in manual mode first. Switch to auto with conservative gains, then optimize
- **Safety systems:** SIL assessment per IEC 61508. Safety functions separate from control functions. SIS (Safety Instrumented Systems) per IEC 61511

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| PID proportional gain Kp | 0.1-100 (process-dependent) | >1000 = check units |
| Integral time Ti | 0.1-1000 s (process-dependent) | <0.01 = noise amplification |
| Derivative time Td | 0 or Ti/4 to Ti/8 | >Ti = unusual, verify |
| Control valve travel time | 2-60 s (full stroke) | <1 = water hammer risk |
| Loop response time | 3-5x valve time | <valve time = cannot achieve |
| Control valve rangeability | 30:1 to 50:1 | <10:1 = poor control at low flow |

## Expert Differentiation

**Expert B (Applied) focus areas:**
- PID tuning in practice (auto-tune, bump tests, lambda tuning)
- Anti-windup schemes (back-calculation, conditional integration, clamping)
- Actuator selection, sizing, and saturation handling
- Sensor noise filtering (moving average, low-pass, deadband)
- Commissioning procedures and field tuning methodology
- Industrial control architectures (DCS, PLC, SCADA, fieldbus)
- Safety Instrumented Systems (SIS) per IEC 61511

## Standards & References

Industry standards for applied control engineering:
- ISA-5.1 (P&ID Symbols), ISA-75 (Control Valves)
- ISA-88 (Batch Control), ISA-95 (Enterprise-Control Integration)
- IEC 61131-3 (PLC Programming), IEC 61511 (Process Industry SIS)
- NEMA ICS (Industrial Control Standards)
- Vendor-specific: Allen-Bradley, Siemens S7, Honeywell Experion, Emerson DeltaV

## Failure Mode Awareness

Practical failure modes to check:
- **Control valve stiction** causes limit cycles — specify smart positioners
- **Sensor drift** over time — specify calibration intervals
- **Network latency** in distributed systems — check loop timing margin
- **Power supply interruption** — specify UPS and fail-safe valve action (fail-open/close)
- **Electromagnetic interference** — check cable routing, shielding, grounding
- **Cybersecurity** for networked control systems — IEC 62443 compliance
"""
    },
    "malzeme": {
        "a": """
## Domain-Specific Methodology

Decision tree for materials analysis:
- **Material selection:** Ashby charts (property mapping), weighted property indices, Cambridge Engineering Selector (CES) methodology
- **Failure analysis:** Examine fracture surface morphology — dimples = ductile, cleavage facets = brittle, striations = fatigue, intergranular = creep/corrosion
- **Phase diagrams:** Lever rule for equilibrium composition. Scheil equation for non-equilibrium solidification (as-cast microstructure)
- **Corrosion assessment:** Pourbaix diagrams for thermodynamic stability. Galvanic series for dissimilar metal contact. Stress corrosion cracking susceptibility maps (material + environment + stress)
- **Heat treatment:** TTT/CCT diagrams for transformation kinetics. Jominy end-quench for hardenability. Tempering parameter (Hollomon-Jaffe) for tempered martensite properties

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Steel density | 7800-7900 kg/m3 | <7000 = wrong alloy class |
| Aluminum density | 2700 kg/m3 | >3000 = wrong material |
| Titanium density | 4500 kg/m3 | >5000 = error |
| Steel CTE | 11-13 um/m/K | >20 = wrong material |
| Fatigue endurance ratio | 0.35-0.60 * UTS | >0.7 = questionable |
| Fracture toughness (steel) | 30-150 MPa*sqrt(m) | <10 = brittle ceramic range |
| Hardness-UTS correlation (steel) | UTS approx 3.45 * HB | >15% deviation = check data |

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Crystal structure and crystallography (FCC, BCC, HCP behavior)
- Dislocation theory and strengthening mechanisms (solid solution, precipitation, work hardening)
- Phase transformation thermodynamics (Gibbs energy, nucleation, growth kinetics)
- Diffusion mechanisms (Fick's laws, activation energy, Arrhenius behavior)
- Mechanical metallurgy (yield criteria, plasticity theory, hardening models)
- Computational materials science (DFT, molecular dynamics, CALPHAD)
- Creep mechanisms (dislocation creep, diffusion creep, Larson-Miller parameter)

## Standards & References

Materials science references:
- ASTM E8/E8M (Tension Testing of Metallic Materials)
- ASTM E23 (Standard Test for Charpy Impact)
- ASTM G48 (Pitting and Crevice Corrosion Resistance)
- ASME SA/SB specifications (Boiler and Pressure Vessel materials)
- AMS specifications (Aerospace Materials — titanium, nickel alloys)
- NACE MR0175/ISO 15156 (Materials for Sour Service)
- ASM Handbook series (comprehensive materials reference)

## Failure Mode Awareness

Known limitations and edge cases:
- **Hydrogen embrittlement** in high-strength steel (>1000 MPa UTS) — may not show in standard testing
- **Sensitization** in austenitic stainless steel (chromium carbide precipitation at 500-800C)
- **Temper embrittlement** (P, Sn, Sb, As segregation at 375-575C)
- **Creep-fatigue interaction** not captured by separate creep or fatigue analysis
- **Galvanic corrosion** rate depends on area ratio — small anode / large cathode is worst case
- **Residual stresses** from welding or forming not usually included in handbook data
""",
        "b": """
## Domain-Specific Methodology

Applied materials engineering approach:
- **Alloy selection for service:** Match material to environment (temperature, corrosion, wear). Start with proven alloys for the application
- **Heat treatment specification:** Specify austenitizing temperature, hold time, cooling rate, tempering temperature for required hardness/toughness combination
- **Welding metallurgy:** Calculate carbon equivalent (CE_IIW or Pcm). Determine preheat requirements. Specify PWHT when required
- **Corrosion protection:** Coating systems (painting, galvanizing, cladding) or material upgrade. Cathodic protection design
- **Materials testing:** Specify test matrix (tensile, Charpy, hardness, corrosion tests). Define acceptance criteria per applicable code

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Carbon equivalent (CE_IIW) | 0.3-0.5 for weldable steel | >0.5 = preheat required |
| Charpy impact at -20C (structural) | 27-100 J | <20 J = brittle concern |
| Hardness HAZ (carbon steel) | 200-350 HV | >350 HV = cracking risk |
| Corrosion rate (mild steel, seawater) | 0.1-0.3 mm/yr | >0.5 = inadequate protection |
| Coating DFT (epoxy system) | 200-400 um | <100 = insufficient protection |
| PWHT temperature (carbon steel) | 580-620 C | >650 = strength reduction |

## Expert Differentiation

**Expert B (Applied) focus areas:**
- Alloy selection for specific service conditions (temperature, environment, loading)
- Heat treatment specifications and process control
- Welding metallurgy (preheat, interpass temp, PWHT, WPS/PQR)
- Corrosion protection systems (coatings, CP, material selection)
- Materials testing (mechanical, corrosion, NDT) — test matrix and acceptance criteria
- Supply chain considerations (material availability, lead times, cost)
- Failure investigation methodology (visual, fractography, metallography, chemical analysis)

## Standards & References

Industry standards for applied materials engineering:
- ASME BPVC Section II (Material Specifications)
- ASTM A20/A370 (Steel plate/testing), ASTM A6 (Structural shapes)
- AWS D1.1 Annex H (Preheat/Interpass Temperature)
- NACE SP0169 (External Corrosion CP), NACE SP0176 (Internal Corrosion)
- SSPC/NACE coating standards (surface preparation, paint systems)
- ISO 9223 (Corrosivity of Atmospheres)

## Failure Mode Awareness

Practical failure modes to check:
- **Under-deposit corrosion** in cooling water systems — check water chemistry and flow velocity
- **Erosion-corrosion** at elbows and restrictions — check flow velocity vs material limits
- **MIC (Microbiologically Influenced Corrosion)** in stagnant water systems
- **Sigma phase** in duplex stainless steels — avoid prolonged exposure to 600-950C
- **Strain aging** in carbon steel — embrittlement after cold working at 150-350C
- **Material substitution risks** — verify equivalent specifications across standards (ASTM/EN/JIS)
"""
    },
    "termodinamik": {
        "a": """
## Domain-Specific Methodology

Decision tree for thermodynamic analysis:
- **Cycle analysis:** Carnot efficiency as theoretical upper bound. Rankine (steam power), Brayton (gas turbine), Otto/Diesel (IC engines), combined cycle (Brayton-Rankine)
- **Working fluid selection:** CoolProp for accurate thermodynamic properties. Ideal gas assumption valid when T >> T_critical AND P << P_critical. Use real gas EOS (Peng-Robinson, SRK) near critical point or at high pressures
- **Heat exchanger design:** LMTD method for known terminal temperatures. NTU-effectiveness method for rating existing exchangers. Kern method for shell-and-tube sizing
- **Psychrometrics:** Wet bulb, dew point, enthalpy of moist air for HVAC design. Use psychrometric chart or ASHRAE relations
- **Exergy analysis:** Second law efficiency reveals true thermodynamic losses. Exergy destruction by component. Grassmann (exergy flow) diagram for system optimization

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| Carnot efficiency | eta_C = 1 - Tc/Th | eta > eta_C = SECOND LAW VIOLATION |
| Steam turbine efficiency | 30-45% (simple Rankine) | >50% single cycle = error |
| Gas turbine efficiency | 35-42% (simple Brayton) | >45% simple cycle = error |
| Combined cycle efficiency | 55-63% | >65% = error |
| Compressor isentropic efficiency | 75-90% | >95% = unrealistic |
| Heat exchanger overall U | 50-500 W/(m2*K) | >2000 = wrong correlation |
| COP refrigeration (vapor compression) | 2-6 | >8 = check calculation |
| Pump efficiency | 60-85% | >95% = unrealistic |

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Gibbs free energy minimization and chemical equilibrium
- Maxwell relations and thermodynamic property derivation
- Fugacity and activity coefficients for non-ideal mixtures
- Statistical thermodynamics (partition functions, molecular interpretation)
- Advanced equations of state (Peng-Robinson, SRK, GERG-2008, PC-SAFT)
- Irreversible thermodynamics (entropy production, Onsager relations)
- Availability (exergy) analysis — dead state definition, chemical exergy

## Standards & References

Thermodynamics engineering references:
- ASME PTC 6 (Steam Turbines — performance testing methodology)
- ASME PTC 22 (Gas Turbines — performance testing)
- ASHRAE 90.1 (Energy Standard for Buildings)
- ISO 5167 (Flow Measurement — orifice, nozzle, venturi)
- API 661 (Air-Cooled Heat Exchangers)
- TEMA (Tubular Exchanger Manufacturers Association — shell-and-tube standards)
- Cengel & Boles, "Thermodynamics" — standard textbook reference

## Failure Mode Awareness

Known limitations and edge cases:
- **Ideal gas assumption** fails near critical point — use real gas EOS (Peng-Robinson, SRK)
- **Constant specific heat** assumption introduces significant error over large temperature ranges (>200K span)
- **Isentropic efficiency** is load-dependent — part-load performance can differ significantly from design point
- **Fouling factors** in heat exchangers increase over time — use TEMA recommended values, not clean conditions
- **Phase change** near critical point is complex — avoid designs operating within 10% of critical pressure/temperature
- **Pinch point** in HRSG design must have minimum temperature approach (typically 8-15 K)
""",
        "b": """
## Domain-Specific Methodology

Applied thermodynamics engineering approach:
- **Industrial cycle optimization:** Start with base cycle, then add feedwater heaters (Rankine), intercooling/regeneration (Brayton). Use vendor data for component efficiencies
- **Heat integration (pinch analysis):** Construct composite curves. Identify minimum utility requirements. Design HEN (Heat Exchanger Network) above and below pinch
- **Equipment sizing:** Use duty (Q) and LMTD to determine required UA. Select exchanger type based on application. Add fouling allowance per TEMA
- **Cost-performance tradeoffs:** Use annualized capital + operating cost for optimization. Higher efficiency equipment costs more — find economic optimum

## Numerical Sanity Checks

Flag results outside these ranges as potential errors:
| Parameter | Typical Range | If Outside |
|-----------|--------------|------------|
| LMTD correction factor F | 0.75-1.0 | <0.75 = redesign needed |
| Fouling resistance (cooling water) | 0.0002-0.0004 m2K/W | >0.001 = severe fouling |
| Approach temperature (cooling tower) | 3-8 K | <2 = uneconomical |
| Pinch temperature (HEN design) | 10-20 K | <5 = excessive HX area |
| Steam quality at turbine exit | >0.88 | <0.85 = blade erosion |
| Condenser pressure | 5-10 kPa (abs) | >15 = poor vacuum |

## Expert Differentiation

**Expert B (Applied) focus areas:**
- Industrial cycle optimization (feedwater heating, reheat, regeneration)
- Heat integration and pinch analysis (composite curves, grand composite)
- Equipment sizing and selection (HX type, pump curves, compressor maps)
- Cost-performance tradeoff analysis (annualized cost optimization)
- Maintenance considerations (fouling, cleaning schedules, spare parts)
- Part-load performance and operational flexibility
- Energy auditing and efficiency improvement identification

## Standards & References

Industry standards for applied thermodynamics:
- TEMA (Heat Exchanger Standards — type selection, fouling factors)
- API 660 (Shell-and-Tube Heat Exchangers — petroleum)
- API 661 (Air-Cooled Heat Exchangers)
- ASME PTC 4.4 (Gas Turbine HRSGs)
- ASHRAE Handbook — HVAC systems and applications
- HEI (Heat Exchange Institute Standards — condensers, feedwater heaters)

## Failure Mode Awareness

Practical failure modes to check:
- **Temperature cross** in heat exchangers — verify LMTD is positive at all points
- **Vibration** in shell-and-tube exchangers (tube bundle natural frequency vs flow-induced excitation)
- **Water hammer** from steam condensation in subcooled lines — install proper drainage
- **Thermal expansion** differential between tubes and shell — verify expansion joint or floating head design
- **Cavitation** in pumps — check NPSHa > NPSHr at all operating conditions
- **Carryover** in boiler drums — check steam quality and drum internals at peak load
"""
    },
}

# ─── Generic template for non-critical domains ──────────────────────────

GENERIC_TEMPLATE_A = """
## Domain-Specific Methodology

[Apply domain-specific method selection based on problem type. Use established analytical frameworks and standard procedures for this engineering discipline.]

## Numerical Sanity Checks

[Check all calculated values against known physical limits and typical engineering ranges. Flag any result that falls outside expected bounds for this domain.]

## Expert Differentiation

**Expert A (Theoretical) focus areas:**
- Governing equations and fundamental theory
- Analytical methods and closed-form solutions
- Mathematical modeling and simulation methodology
- Derivation from first principles
- Theoretical limitations and assumptions

## Standards & References

[Reference applicable industry standards, codes, and established engineering references for this domain.]

## Failure Mode Awareness

[Identify known limitations of standard analysis methods in this domain. Flag edge cases where common assumptions break down.]
"""

GENERIC_TEMPLATE_B = """
## Domain-Specific Methodology

[Apply practical engineering methods appropriate for the problem. Use industry-standard design procedures and proven approaches for this discipline.]

## Numerical Sanity Checks

[Verify all results against practical experience and field data. Flag any values that conflict with established engineering practice in this domain.]

## Expert Differentiation

**Expert B (Applied) focus areas:**
- Industry-standard design procedures and codes
- Practical implementation and field experience
- Equipment selection and sizing
- Cost-effective solutions and optimization
- Safety, maintenance, and operational considerations

## Standards & References

[Reference applicable industry codes, manufacturer guidelines, and field-proven practices for this domain.]

## Failure Mode Awareness

[Identify practical failure modes encountered in field applications. Flag common design mistakes and operational issues in this domain.]
"""


def enrich_file(filepath: str, content: str, dry_run: bool = True) -> bool:
    """Append enrichment content to a SKILL.md file if not already present."""
    with open(filepath, "r", encoding="utf-8") as f:
        existing = f.read()

    if "## Domain-Specific Methodology" in existing:
        return False  # Already enriched

    new_content = existing.rstrip() + "\n" + content.strip() + "\n"

    if dry_run:
        print(f"  [DRY RUN] Would enrich: {filepath}")
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  [UPDATED] {filepath}")
    return True


def main():
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN — pass --apply to write changes\n")
    else:
        print("APPLYING CHANGES\n")

    updated = 0
    skipped = 0
    total = 0

    # Walk all domain SKILL.md files
    for skill_path in sorted(glob.glob(os.path.join(AGENTS_DIR, "*", "*", "SKILL.md"))):
        total += 1
        # Extract domain and tier from path
        parts = skill_path.replace(os.sep, "/").split("/")
        # ...agents/domain/<domain>/<domain>_<a|b>/SKILL.md
        agent_dir = parts[-2]  # e.g., "yanma_a"
        domain_dir = parts[-3]  # e.g., "yanma"

        tier = "a" if agent_dir.endswith("_a") else "b"

        # Get domain-specific content or generic
        if domain_dir in DOMAIN_ENRICHMENTS:
            content = DOMAIN_ENRICHMENTS[domain_dir].get(tier, "")
        else:
            content = GENERIC_TEMPLATE_A if tier == "a" else GENERIC_TEMPLATE_B

        if not content:
            content = GENERIC_TEMPLATE_A if tier == "a" else GENERIC_TEMPLATE_B

        if enrich_file(skill_path, content, dry_run):
            updated += 1
        else:
            skipped += 1
            if not dry_run:
                print(f"  [SKIPPED] {skill_path} (already enriched)")

    print(f"\nTotal: {total} files, Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
