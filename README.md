# Creator Hive — Enterprise Creator-Economy Operating System

Creator Hive is a two-sided marketplace and collaboration operating system built to connect enterprise brands and verified creators with institutional data fidelity.

---

### Architecture & Engineering Highlights
- **Consolidated Production Engine (`app.py`)**: Fully unified backend, relational schema, role-based authorization, REST API suite, and embedded SPA frontend.
- **Relational Integrity**: 20+ normalized relational tables built on SQLAlchemy 2.0 with strict foreign key cascading, indexed queries, and local SQLite auto-fallback.
- **Enterprise Creator Onboarding**: Modern frictionless creator sign-up (basic identity only), shifting social channels, categories, niches, and pricing to the post-authentication workspace.
- **Collab Intelligence™**: Platform score computed from real database transaction histories: Category Fit, Response Rate, Deadline Reliability, and Historical Completion.
- **Relationship Memory™**: Persistent multi-campaign relationship ledger tracking communication histories, deal submissions, feedback, and notes between brands and creators.

---

### Local Development Setup

1. **Clone & Virtual Environment**:
   ```powershell
   git clone <repo-url>
   cd creator-hive
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate