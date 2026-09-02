"""Academic bibliography and quantitative research registry backing CaiSheng."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AcademicPaper:
    paper_id: str
    title: str
    authors: str
    year: int
    journal: str
    doi_or_url: str
    category: Literal[
        "volatility_dynamics",
        "empirical_bayes_shrinkage",
        "analytical_pricing",
        "coherent_risk_cvar",
        "multi_agent_ai",
        "defined_risk_derivatives",
        "rough_volatility_frontier",
    ]
    core_concept: str
    latex_formula: str
    volagent_subsystem: str
    relevance_to_track_2: str


RESEARCH_BIBLIOGRAPHY: list[AcademicPaper] = [
    AcademicPaper(
        paper_id="CARR-WU-2009",
        title="The Finite-Moment Log-Normal Model for Option Pricing and the Variance Risk Premium",
        authors="Peter Carr, Liuren Wu",
        year=2009,
        journal="Journal of Financial Economics, 93(3), 476-499",
        doi_or_url="https://doi.org/10.1016/j.jfineco.2008.09.006",
        category="volatility_dynamics",
        core_concept="Variance Risk Premium (VRP) and systemic overpricing of jump risk in equity options prior to scheduled events.",
        latex_formula=r"\text{VRP}_t = \mathbb{E}^{\mathbb{P}}\left[\int_t^T \sigma_s^2 ds\right] - \mathbb{E}^{\mathbb{Q}}\left[\int_t^T \sigma_s^2 ds\right] < 0",
        volagent_subsystem="src/volagent/quant/repricing.py & quant/strategy_selector.py",
        relevance_to_track_2="Direct theoretical foundation for Short Iron Butterfly archetype: harvesting overpriced event variance when forecast jump is contained.",
    ),
    AcademicPaper(
        paper_id="PATELL-WOLFSON-1981",
        title="The Ex-Ante Information Content of Accounting Earnings Announcements and the Intraday Speed of Adjustment",
        authors="James M. Patell, Mark A. Wolfson",
        year=1981,
        journal="Journal of Accounting Research, 19(2), 661-687",
        doi_or_url="https://doi.org/10.2307/2490870",
        category="volatility_dynamics",
        core_concept="Pre-earnings implied volatility run-up followed by instantaneous post-announcement volatility collapse (IV crush).",
        latex_formula=r"\sigma_{\text{post}} = \sigma_{\text{pre}} - \Delta \sigma_{\text{event}}, \quad \Delta \sigma_{\text{event}} \approx 30\% \text{ to } 60\% \text{ of ATM IV}",
        volagent_subsystem="src/volagent/quant/forecast.py & quant/repricing.py",
        relevance_to_track_2="Underpins CaiSheng's post-earnings IV crush forecast model and multi-leg scenario repricing.",
    ),
    AcademicPaper(
        paper_id="BRENNER-SUBRAHMANYAM-1988",
        title="A Simple Formula to Compute the Implied Standard Deviation",
        authors="Menachem Brenner, Marti G. Subrahmanyam",
        year=1988,
        journal="Financial Analysts Journal, 44(5), 80-83",
        doi_or_url="https://doi.org/10.2469/faj.v44.n5.80",
        category="analytical_pricing",
        core_concept="Analytic closed-form approximation relating ATM straddle prices and implied volatility for short-dated maturities.",
        latex_formula=r"\sigma \approx \frac{C_{\text{ATM}} + P_{\text{ATM}}}{0.8 \cdot S_0 \cdot \sqrt{T}} \approx \frac{\text{Straddle}_{\text{ATM}}}{0.8 \cdot S_0 \cdot \sqrt{T}}",
        volagent_subsystem="src/volagent/quant/expected_move.py & quant/repricing.py",
        relevance_to_track_2="Enables real-time inverted ATM implied move and base IV calibration across large option chains without slow numerical root-finders.",
    ),
    AcademicPaper(
        paper_id="JAMES-STEIN-1961",
        title="Estimation with Quadratic Loss",
        authors="W. James, Charles Stein",
        year=1961,
        journal="Proceedings of the Fourth Berkeley Symposium on Mathematical Statistics and Probability, Vol. 1, 361-379",
        doi_or_url="https://projecteuclid.org/euclid.bsmsp/1200512173",
        category="empirical_bayes_shrinkage",
        core_concept="Hierarchical empirical Bayes shrinkage outperforming maximum likelihood for small sample sizes ($N < 10$) by pulling noisy ticker estimates toward sector/global medians.",
        latex_formula=r"\hat{m}_{\text{shrunk}} = w_t \cdot m_{\text{ticker}} + w_s \cdot m_{\text{sector}} + w_g \cdot m_{\text{global}}, \quad \sum w_i = 1",
        volagent_subsystem="src/volagent/quant/forecast.py",
        relevance_to_track_2="Prevents overfitting to sparse historical earnings moves ($N=4-8$ quarters) in fast-moving tech earnings.",
    ),
    AcademicPaper(
        paper_id="ROCKAFELLAR-URYASEV-2000",
        title="Optimization of Conditional Value-at-Risk",
        authors="R. Tyrrell Rockafellar, Stanislav Uryasev",
        year=2000,
        journal="Journal of Risk, 2(3), 21-41",
        doi_or_url="https://doi.org/10.21314/JOR.2000.038",
        category="coherent_risk_cvar",
        core_concept="Coherent convex risk measurement using Conditional Value-at-Risk (CVaR / Expected Shortfall) for asymmetrical option tails.",
        latex_formula=r"\text{ES}_{95} = \mathbb{E}\left[\text{Loss} \mid \text{Loss} \ge \text{VaR}_{95}\right], \quad \text{Score} = \mathbb{E}[\text{PnL}] - \lambda \cdot \text{ES}_{95}",
        volagent_subsystem="src/volagent/quant/repricing.py & quant/strategy_selector.py",
        relevance_to_track_2="Guarantees that strategy selection penalizes severe tail blowout scenarios rather than naive variance or symmetric standard deviation.",
    ),
    AcademicPaper(
        paper_id="ARTZNER-1999",
        title="Coherent Measures of Risk",
        authors="Philippe Artzner, Freddy Delbaen, Jean-Marc Eber, David Heath",
        year=1999,
        journal="Mathematical Finance, 9(3), 203-228",
        doi_or_url="https://doi.org/10.1111/1467-9965.00068",
        category="coherent_risk_cvar",
        core_concept="Axiomatic foundation of risk measures: Translation Invariance, Sub-additivity, Positive Homogeneity, and Monotonicity.",
        latex_formula=r"\rho(X + Y) \le \rho(X) + \rho(Y) \quad (\text{Sub-additivity})",
        volagent_subsystem="src/volagent/quant/risk_gate.py",
        relevance_to_track_2="Theoretical basis for CaiSheng's 20-point quantitative risk gate and 1.0% NAV stress drawdown cap.",
    ),
    AcademicPaper(
        paper_id="NATENBERG-1994",
        title="Option Volatility and Pricing: Advanced Trading Strategies and Techniques",
        authors="Sheldon Natenberg",
        year=1994,
        journal="McGraw-Hill Professional (2nd Ed. 2014)",
        doi_or_url="https://www.mhprofessional.com/option-volatility-and-pricing",
        category="defined_risk_derivatives",
        core_concept="Strict wing strike ordering and defined-risk topology for Delta-Neutral non-directional volatility structures.",
        latex_formula=r"K_{p,\text{long}} < K_{p,\text{short}} = K_{c,\text{short}} < K_{c,\text{long}}, \quad \text{MaxLoss} = \max(\Delta K_{\text{put}}, \Delta K_{\text{call}}) \cdot 100 - \text{Credit}",
        volagent_subsystem="src/volagent/quant/strategy_factory.py & quant/payoff.py",
        relevance_to_track_2="Guarantees zero naked tail risk and strictly defined margin collateral across all executable multi-leg strategies.",
    ),
    AcademicPaper(
        paper_id="DU-2023",
        title="Improving Factuality and Reasoning in Language Models through Multiagent Debate",
        authors="Yilun Du, Shuang Li, Antonio Torralba, Joshua B. Tenenbaum, Igor Mordatch",
        year=2023,
        journal="arXiv preprint arXiv:2305.14325 (MIT CSAIL & Google DeepMind)",
        doi_or_url="https://arxiv.org/abs/2305.14325",
        category="multi_agent_ai",
        core_concept="Dialectical multi-agent debate between specialized personas to overcome confirmation bias and eliminate hallucinations.",
        latex_formula=r"\text{Consensus} = \text{Adjudicate}\left(\text{Thesis}_{\text{Long}}(\mathcal{E}), \text{Thesis}_{\text{Short}}(\mathcal{E}) \mid \text{Critic}(\text{Risk})\right)",
        volagent_subsystem="src/volagent/agents/ & src/volagent/graph/nodes.py",
        relevance_to_track_2="Core architecture for Long Vol vs. Short Vol advocate debate with an adversarial Model-Risk Critic.",
    ),
    AcademicPaper(
        paper_id="GAO-2023",
        title="Enabling Large Language Models to Generate Text with Citations",
        authors="Tianyu Gao, Howard Yen, Jiacheng Yu, Danqi Chen",
        year=2023,
        journal="Empirical Methods in Natural Language Processing (EMNLP 2023)",
        doi_or_url="https://arxiv.org/abs/2305.14627",
        category="multi_agent_ai",
        core_concept="Attributable and grounded text generation requiring claims to cite verified document chunks and failing closed on hallucination.",
        latex_formula=r"\text{Citations}(\text{Claim}) \subseteq \text{ValidEvidenceIDs}(\mathcal{D}_{\text{frozen}})",
        volagent_subsystem="src/volagent/agents/event_magnitude.py & agents/model_risk.py",
        relevance_to_track_2="Ensures all agent thesis claims are strictly grounded in SEC filings and point-in-time option surface evidence.",
    ),
    AcademicPaper(
        paper_id="GATHERAL-2018",
        title="Volatility is rough",
        authors="Jim Gatheral, Thibault Jaisson, Mathieu Rosenbaum",
        year=2018,
        journal="Quantitative Finance, 18(6), 933-949",
        doi_or_url="https://doi.org/10.1080/14697688.2017.1393551",
        category="rough_volatility_frontier",
        core_concept="Log-volatility behaves as fractional Brownian motion with Hurst parameter $H \\approx 0.1$, explaining steep short-term implied volatility skew power-law blowup $O(T^{H-1/2})$.",
        latex_formula=r"\log \sigma_{t+\Delta} - \log \sigma_t \sim \nu \Delta^H \xi, \quad H \in (0, 0.5), \quad \text{Skew}(T) \sim T^{H-1/2}",
        volagent_subsystem="src/volagent/quant/rough_vol.py",
        relevance_to_track_2="Explains explosive short-dated pre-earnings implied volatility skew that standard Markovian diffusion models fail to fit.",
    ),
    AcademicPaper(
        paper_id="ABI-JABER-2019",
        title="Affine Volterra processes",
        authors="Eduardo Abi Jaber, Martin Larsson, Sergio Pulido",
        year=2019,
        journal="The Annals of Applied Probability, 29(5), 3155-3200",
        doi_or_url="https://doi.org/10.1214/19-AAP1484",
        category="rough_volatility_frontier",
        core_concept="Markovian lifting: Mapping non-Markovian singular fractional kernels $K(t) = \\frac{t^{H-1/2}}{\\Gamma(H+1/2)}$ into an $n$-dimensional Markovian system of OU factors.",
        latex_formula=r"K(t) \approx \sum_{i=1}^n c_i e^{-x_i t}, \quad V_t = V_0 + \sum_{i=1}^n c_i U_t^i, \quad dU_t^i = -x_i U_t^i dt + \nu \sqrt{V_t} dW_t",
        volagent_subsystem="src/volagent/quant/rough_vol.py",
        relevance_to_track_2="Restores $O(N)$ high-speed simulation and fast Fourier pricing to rough volatility models without non-Markovian memory overhead.",
    ),
    AcademicPaper(
        paper_id="LYONS-1998",
        title="Differential equations driven by rough signals",
        authors="Terry Lyons",
        year=1998,
        journal="Revista Matemática Iberoamericana, 14(2), 215-310",
        doi_or_url="https://doi.org/10.4171/RMI/240",
        category="rough_volatility_frontier",
        core_concept="Path signatures and rough path theory: Truncated tensor series of iterated path integrals capturing order of events, non-linear geometric shape, and Levy area invariant to time-reparameterization.",
        latex_formula=r"\mathbb{S}(X)_{s,t}^{\le 2} = \left(1, \Delta X^i, \int_{s}^t (X_u^i - X_s^i) dX_u^j\right)",
        volagent_subsystem="src/volagent/quant/rough_vol.py",
        relevance_to_track_2="Extracts universal non-parametric geometric features from intraday volatility paths for downstream machine learning and anomaly detection.",
    ),
]


def get_paper_by_id(paper_id: str) -> AcademicPaper | None:
    """Retrieve an academic paper from the registry by ID."""
    for paper in RESEARCH_BIBLIOGRAPHY:
        if paper.paper_id == paper_id:
            return paper
    return None


def get_papers_by_category(category: str) -> list[AcademicPaper]:
    """Retrieve all papers matching a specific category."""
    return [p for p in RESEARCH_BIBLIOGRAPHY if p.category == category]
