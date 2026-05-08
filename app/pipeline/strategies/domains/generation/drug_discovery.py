"""Drug discovery generation sub-strategy module."""

CATEGORY = "generation"
NAME = "drug_discovery"
DISPLAY_NAME = "Drug Discovery Research"
DESCRIPTION = (
    "Maps the drug discovery landscape for a target or disease area, covering "
    "mechanism of action, pipeline compounds, clinical trial status, and "
    "safety signals. Supports hypothesis generation for novel therapeutic approaches."
)
SELECTORS = [
    "target_protein",
    "disease_indication",
    "mechanism_of_action",
    "compound_name",
    "clinical_trial_phase",
    "safety_signal",
    "research_institution",
]

STRATEGY = """
=== DRUG DISCOVERY RESEARCH STRATEGY ===

This strategy maps the scientific and commercial landscape of drug discovery for
a given target or disease indication. It covers validated targets, known compounds,
clinical pipeline status, safety signals, and research frontiers. The output supports
hypothesis generation for novel therapeutic approaches. This is for research and
informational purposes only — not medical advice. Validate coverage using the
completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step drug discovery research process:

1. TARGET & DISEASE SCOPING — Establish the biological context:
   - Define the disease indication and patient population
   - Identify the molecular target (protein, receptor, enzyme, nucleic acid)
   - Map the target's biological pathway and disease mechanism
   - Assess target validation evidence: genetic association, animal model data,
     biomarker correlation, prior clinical success/failure
   - Identify alternative targets in the same pathway as fallback options

2. COMPOUND LANDSCAPE MAPPING — Survey known compounds addressing the target:
   - Approved drugs: FDA Orange Book, EMA medicines database
   - Patent-protected pipeline: patent literature (Google Patents, Espacenet)
   - Clinical pipeline: ClinicalTrials.gov, WHO International Clinical Trials Registry
   - Research compounds: ChEMBL, DrugBank, PubChem for structure-activity data
   Classify compounds by: development stage, mechanism of action, and structural class.

3. CLINICAL TRIAL INTELLIGENCE — Map the clinical evidence base:
   - Active and completed trials: ClinicalTrials.gov by condition and intervention
   - Phase distribution: how many compounds at each clinical stage
   - Trial outcomes: published efficacy and safety data (PubMed, ClinicalTrials results)
   - Failed trials: identify failure reasons (efficacy, safety, commercial, enrollment)
   - Biomarker strategies: predictive biomarkers for patient stratification

4. SAFETY SIGNAL ASSESSMENT — Identify known and potential safety concerns:
   - FDA adverse event data (FAERS database) for approved and investigational drugs
   - EMA EPAR assessments for European approvals
   - Published safety studies and post-marketing surveillance reports
   - Target-related toxicology: on-target vs. off-target safety concerns
   - Black box warnings and regulatory risk mitigation strategies (REMS)

5. RESEARCH FRONTIER IDENTIFICATION — Locate the leading edge of the field:
   - Recent high-impact publications (Nature, Science, Cell, NEJM, Lancet, JAMA)
   - Preprints on bioRxiv / medRxiv for unpublished data
   - Grant funding databases (NIH Reporter, EU Horizon) for funded research directions
   - Conference abstracts (ASHP, ACS, AACR, ESC, ASH, etc.) for emerging data
   - Key opinion leaders and research groups driving the field

--- PRIORITY SELECTORS (Drug Discovery Research) ---

Ordered by research leverage (highest first):

1. target_protein         — molecular anchor for mechanism and compound landscape
2. disease_indication     — clinical context; scopes trial, safety, and commercial data
3. mechanism_of_action    — mechanistic framework; groups compounds by approach
4. compound_name          — specific compound or drug class for focused intelligence
5. clinical_trial_phase   — pipeline maturity filter for competitive intelligence
6. safety_signal          — known adverse effects guiding differentiation strategy
7. research_institution   — key academic and industry groups driving the field

--- KEY PIVOT PATTERNS ---

target_protein:
  - UniProt (uniprot.org) for protein function, structure, and known interactions
  - ChEMBL (ebi.ac.uk/chembl) for bioactivity data on compounds against the target
  - DrugBank (drugbank.com) for approved drugs and their primary/secondary targets
  - PubMed: ddg_search "site:pubmed.ncbi.nlm.nih.gov [target] [disease]"

disease_indication:
  - ClinicalTrials.gov: search by condition with filters for phase and status
  - WHO International Clinical Trials Registry Platform (ICTRP)
  - FDA Drug Trials Snapshots for demographic breakdowns of approved drug trials
  - google_news "[disease] drug approval" OR "[disease] clinical trial results"

compound_name:
  - PubChem (pubchem.ncbi.nlm.nih.gov) for chemical structure and bioactivity
  - DrugBank for mechanism, targets, interactions, and pharmacokinetics
  - ClinicalTrials.gov intervention name search for trial history
  - FDA Orange Book (drugs@fda) for approved formulations and patent expiry

clinical_trial_phase:
  - ClinicalTrials.gov advanced search: filter by condition + phase + status
  - Citeline Pharma Intelligence (subscription) for comprehensive pipeline data
  - Evaluate Pharma (subscription) for commercial pipeline analytics
  - web_search_fetch "[company] pipeline" page for company-disclosed trial status

safety_signal:
  - FDA FAERS database (fda.gov/drugs/questions-and-answers-fdas-adverse-event) for AE reports
  - EudraVigilance for European adverse event data
  - PubMed: ddg_search "[compound] adverse effects" OR "[compound] toxicity"
  - FDA drug label (Prescribing Information) for approved drug safety sections

--- COMPLETENESS CHECKLIST ---

Before closing a drug discovery research task, confirm coverage in each area:

1. Target Validation     — biological target identified; validation evidence assessed
2. Compound Landscape    — approved drugs and development-stage compounds mapped
3. Clinical Pipeline     — trial phase distribution documented; key trials identified
4. Safety Profile        — known adverse effects and regulatory signals documented
5. Research Frontier     — recent publications and emerging approaches identified
6. Competitive Summary   — key players (pharma, biotech, academic) and their programs listed

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED

DISCLAIMER: This output is for research and informational purposes only.
It does not constitute medical advice or clinical guidance.
"""
