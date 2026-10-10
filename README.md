# Academic-Scientist Agent Skill

**Turn a broad research interest and a folder of papers into an evidence-linked literature library and an editable research framework.**

English · [简体中文](README.zh-CN.md)

**V0.1** · **For Codex** · **MIT** · **Invoke with `$academic-scientist`**

[Quick start](#quick-start) · [Workflow](#workflow) · [What you receive](#what-you-receive) · [Requirements](#requirements-and-current-limits)

Academic-Scientist is a local Codex skill for graduate students and researchers who need help finding a useful reading direction, understanding supplied papers, and developing a research plan. You can begin with an uncertain idea: three rounds of conversation help clarify what to learn next.

> Read with evidence. Keep unknowns visible. Build a plan you can revise.

## Why use it?

| Your starting point | How the skill helps |
|---|---|
| “I am interested in this area, but I do not have a precise question.” | Three adaptive discussion rounds turn your real answers into a research profile, retaining unresolved choices. |
| “I have many papers and keep losing track of their methods.” | Structured reading cards capture methods, model origins, experimental conditions and findings, with source locations. |
| “I do not know what this journal or conference represents.” | A separate venue card explains its scope and the latest officially verifiable ratings. |
| “I want to edit my literature table as my understanding changes.” | Edit Excel fact cells and separate notes; factual revisions are checked against the paper before merging. |
| “What can I learn from these papers for my own work?” | Learning reasons cover methods, background, experimental design and model choice, without scores or rankings. |
| “I need a concrete framework to discuss with my advisor.” | Confirm one route, then receive a proposed study and three editable diagram views. |

The workflow is suited to both computational papers and experiment-heavy literature. A paper without a computational model is allowed to have **not applicable** model fields.

## Workflow

![Academic-Scientist workflow: research curiosity and supplied papers lead to evidence-linked guidance, a confirmed route and three editable views.](assets/workflow.svg)

[Full-size PNG](assets/workflow.png) · [Editable draw.io source](assets/workflow.drawio) · [PDF](assets/workflow.pdf)

This is a conceptual workflow illustration. It contains no research findings. Solid arrows indicate process or evidence use; dashed arrows carry research goals or external context.

1. **Explore the question.** The Agent asks three rounds of follow-up questions, one round at a time, and waits for your answers. The questions adapt to your experience and uncertainties.
2. **Read the supplied papers.** Inspect text, tables and figures; record the source of each extracted item and what could not be established.
3. **Add official venue context.** Keep journal/conference scope and ratings separate from paper facts. Retain the rating system, edition, subject category and query date.
4. **Maintain an editable library.** Export reading cards and Excel; retain evidence, edit baselines and revision history for later updates.
5. **Explain what is useful.** Connect paper evidence to your goals, with learning reasons, reading locations and conditions for transferring a method.
6. **Confirm a research route.** Ask about consequential unknowns before creating one detailed framework. Keep proposed designs separate from published findings.
7. **Deliver three diagram views.** Generate an overall framework, a key-module detail and an experimental workflow from the same proposal and evidence.

## Evidence comes first

The skill keeps four kinds of information separate:

| Information | Source and handling |
|---|---|
| **Paper facts** | Only the papers and supplementary material you provide. Preserve page, section, table or figure references and supporting evidence. |
| **External venue context** | Official sources only. Show the latest verifiable version; if unavailable, explicitly report “尚未查阅到相关官方评级” (no relevant official rating verified). Do not substitute third-party ratings. |
| **Agent analysis and proposals** | Identify supporting facts, assumptions, transfer conditions and open questions. A proposal is not an executed experiment. |
| **Your notes and revisions** | Keep notes independent. Recheck factual edits against the original paper and surface conflicts before merging. |

Extraction includes title, authors, formal publication year, journal/conference, research purpose, methods, models and their provenance, data/materials, parameters, metrics with experimental conditions, results and limitations. Code/data fields record **whether the paper states they are provided**, not whether those resources have been independently tested.

Model provenance distinguishes a new architecture/module, structural modification, combination, fine-tuning/training changes, direct use, a comparison baseline, and insufficient evidence. “The authors propose” does not independently establish novelty.

**Not reported, not applicable, uncertain and not yet inspected are different states.** Evidence and Agent review support checking; they do not guarantee correctness or replace expert judgment.

## What you receive

| Deliverable | Purpose |
|---|---|
| Research profile | Preserve your goals, real answers, constraints and unresolved questions. |
| Paper reading cards | Revisit each paper's claims and evidence. |
| Excel + Markdown literature library | Compare papers, edit fact cells and maintain personal notes. |
| Reading guidance | Learn from methods, background, experimental design and model choices; no numerical scoring or strength ranking. |
| Research proposal | Discuss a question, hypotheses, methods, controls, evaluation, a minimal experiment and failure criteria. |
| Three editable diagrams | Overall framework, key-module detail and experimental workflow; draw.io and SVG, with PNG/PDF when rendering is available. |

A study workspace keeps everyday outputs near the top and internal records below. The default output filenames are Chinese:

```text
my-research-project/
├── 阅读入口.md          # Start here
├── 研究档案.md          # Research profile
├── 文献整理.xlsx        # Editable literature table
├── 阅读建议.md          # Reading guidance
├── 研究方案.md          # Proposed study
├── 论文阅读卡/          # Paper reading cards
├── 流程图/              # Editable diagrams and exports
└── .academic-scientist/ # Evidence, state, baselines and history
```

Files appear as the relevant work is completed. Keep the internal directory to support resuming and reconciling edits. Existing user edits are protected; old study workspaces are not automatically migrated.

## Quick start

### 1. Get the repository

Download and extract **Code → Download ZIP**, or clone it:

```powershell
git clone --config core.autocrlf=false https://github.com/Emphany-Go/Academic-Scientist-Agent-Skill.git
cd Academic-Scientist-Agent-Skill
```

The clone option preserves line endings for the file-integrity check. Use the folder containing `README.md`, `skills/` and `tools/`. You do not need to create a GitHub Release to use this source package.

### 2. Check the package and install the skill

```powershell
python -B -X utf8 tools/self_check.py
python -B -X utf8 tools/install.py
```

The bundled installer defaults to `~/.agents/skills/academic-scientist`. If your client uses `~/.codex/skills`, see the compatibility option in the [installation guide](docs/INSTALL.md). It refuses to overwrite an existing same-name skill. Choose one installation location; the installer copies skill files and does not install runtime dependencies.

Open a new Codex conversation and use `$academic-scientist`. Check the actual client's skill list if it is not recognized.

### 3. Start with your question and papers

```text
Use $academic-scientist.
I am interested in [broad research area], but I have not chosen a precise question.
My papers are in [paper folder]. Work in [research project folder].
First check the environment and tell me about any missing capabilities.
Then guide me through three discussion rounds, waiting for my real answers.
Read the supplied papers and retain source evidence and uncertainty.
Ask before making unresolved choices that affect the research.
```

Use a research directory separate from the installed skill. Conversation and outputs can follow your requested language. Research figures default to Chinese with necessary English terms; explicitly request English labels if you prefer them.

## Prompts for ongoing work

**Update a literature table**

```text
I edited the fact cells and notes in 文献整理.xlsx.
Compare them with the export baseline and current records.
Check factual edits against the supplied papers and ask me about conflicts.
```

**Change the reading direction**

```text
My research goal has changed to [new direction].
Preserve the verified paper facts, update my research profile,
and regenerate the learning reasons for this goal without scores or rankings.
```

**Develop a framework with diagrams**

```text
Use the reviewed papers and reading guidance to help me select one research route.
Ask about consequential unknowns first, then build one detailed proposal.
Deliver the overall framework, key-module detail and experimental workflow together.
Use English diagram labels and provide editable draw.io sources.
Separate literature evidence, proposed designs and unresolved assumptions.
```

## Requirements and current limits

| Capability | Required environment |
|---|---|
| Reading and research discussion | Codex with local file/script access and visual inspection; web tools for official venue lookups. |
| State, validation and PDF processing | Python 3.10+; `jsonschema`, `pypdf`, `pypdfium2`, `Pillow`. Tested versions are in [requirements.txt](skills/academic-scientist/requirements.txt). |
| Excel generation | Node.js and an existing host-provided `@oai/artifact-tool` runtime. |
| PNG/PDF figure rendering | Node.js, Playwright and an available Chrome/Chromium browser. |

**Installing the skill does not install these runtimes.** In particular, do not assume `@oai/artifact-tool` is available from public npm. The environment checker reports missing components; dependency installation requires your confirmation. Without the Excel runtime, JSON/Markdown work can continue, but new XLSX generation is unavailable.

The Agent performs semantic reading and official-source research; the scripts handle state, validation and export. V0.1 does not run OCR, train models, execute the proposed experiments or establish novelty automatically. It is a local skill package, not a standalone model service or a published Codex plugin.

The V0.1 release recorded **321 automated tests and 33 release checks**, plus archive and isolated-installation checks, in the tested Windows/Python 3.11 environment. These are historical release checks, not an extraction-accuracy claim or a fresh full-workflow evaluation of this README update. Native draw.io application behavior, cross-machine deployment and some user acceptance scenarios remain unverified. See [validation scope](VALIDATION.md) and [release notes](docs/RELEASE_NOTES.md).

## Repository map

```text
Academic-Scientist-Agent-Skill/
├── README.md / README.zh-CN.md
├── assets/                     # English workflow and editable source
├── skills/academic-scientist/   # Installable skill, scripts, schemas and references
├── tools/                      # Package check and local installer
├── docs/                       # Installation, publishing and release notes
├── SHA256SUMS.json             # File-integrity manifest
└── LICENSE                     # MIT
```

The source package excludes research PDFs, personal answers, study workspaces, benchmark data and development logs. This documentation refresh keeps the V0.1 skill implementation unchanged. Supporting operational documents are currently in Chinese.

## Documentation and acknowledgments

- [Installation and environment setup](docs/INSTALL.md)
- [V0.1 release notes](docs/RELEASE_NOTES.md)
- [Validation scope](VALIDATION.md)
- [Reference and dependency notices](NOTICE.md)

The project drew workflow inspiration from [Academic Research Agent Skill](https://github.com/ngtiendong/Academic-Research-Agent-Skill). This README also learns from its use-case-led presentation. The capability descriptions here apply to this repository's own implementation.

Released under the [MIT License](LICENSE).
