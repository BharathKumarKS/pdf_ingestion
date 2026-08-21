# Cline Agent Guidelines for Data Science Projects

## Role & Context
You are assisting a data scientist working on:
- Python data manipulation and analysis
- SQL querying and optimization
- Machine learning model development
- Gen AI projects
- Technical interview preparation

## Working Principles

### 1. Plan Mode First, Always
- **NEVER** jump straight into Act mode
- Always start in Plan mode to explore the codebase and understand requirements
- Create a detailed implementation plan in a `.md` file before any code changes
- Review and refine the plan with me before switching to Act mode
- A 30-second planning conversation saves 10 minutes of wrong-direction implementation

### 2. Code Quality Standards
- Follow PEP 8 style guidelines for Python code
- Use type hints for all function signatures
- Include docstrings for all functions and classes (Google or reStructuredText style)
- Write modular, testable code with single-responsibility functions
- Prefer list comprehensions over explicit loops where readable
- Use f-strings for string formatting (Python 3.6+)

### 3. Project Structure Conventions
```
project_root/
├── src/
│   ├── __init__.py
│   ├── data/          # Data loading and preprocessing
│   ├── models/        # Model definitions
│   ├── utils/         # Helper functions
│   └── features/      # Feature engineering
├── notebooks/         # Jupyter notebooks for exploration
├── tests/             # Unit tests (pytest)
├── config/            # Configuration files
├── data/              # Raw and processed data (gitignored)
├── .env               # Environment variables
├── pyproject.toml     # Project metadata and dependencies (uv)
├── uv.lock            # Lock file for reproducible installs (uv)
├── .python-version    # Python version specification (uv)
└── README.md          # Project documentation
```

### 4. Python & uv Project Management

#### uv Setup & Configuration
- Use `uv` as the primary project and package manager
- Initialize new projects with: `uv init <project_name>`
- Create virtual environments with: `uv venv` (or let uv manage it automatically)
- Activate virtual environment: `source .venv/bin/activate` (MacOS/Linux) or `.venv\Scripts\activate` (Windows)
- Use `uv run <command>` to execute commands in the project's virtual environment
- Use `uv add <package>` to add dependencies to `pyproject.toml`
- Use `uv remove <package>` to remove dependencies
- Use `uv sync` to install dependencies from `pyproject.toml` and `uv.lock`
- Use `uv pip install -r requirements.txt` only when migrating from pip-based projects
- Use `uv export > requirements.txt` to generate requirements.txt for compatibility

#### pyproject.toml Standards
- Define project metadata (name, version, description, authors)
- Specify Python version requirement: `requires-python = ">=3.10"`
- List dependencies in `[project.dependencies]`
- List dev dependencies in `[project.optional-dependencies.dev]` or `[tool.uv.dev-dependencies]`
- Configure linting, formatting, and testing tools in `[tool.*]` sections

#### Example pyproject.toml Structure
```toml
[project]
name = "your-project-name"
version = "0.1.0"
description = "Brief project description"
requires-python = ">=3.10"
dependencies = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "flake8>=6.1.0",
    "mypy>=1.5.0",
    "ipykernel>=6.25.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "flake8>=6.1.0",
    "mypy>=1.5.0",
]

[tool.black]
line-length = 88
target-version = ["py310"]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

#### Environment Management
- Always use `uv run` for commands to ensure correct environment
- Add environment variables to `.env` file (gitignored)
- Load environment variables using `python-dotenv` in code
- Use `uv run python -m dotenv run -- python your_script.py` for dotenv integration

### 5. Python Best Practices
- Always use virtual environments managed by uv
- Load environment variables using `python-dotenv`
- Use `pathlib.Path` instead of `os.path` for file operations
- Implement proper error handling with specific exception types
- Use context managers (`with` statements) for file and resource handling
- Add logging instead of print statements for production code
- Use `logging` module with appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### 6. SQL Guidelines
- Use parameterized queries to prevent SQL injection
- Write readable, well-formatted SQL with proper indentation
- Use Common Table Expressions (CTEs) for complex queries
- Add comments for non-trivial query logic
- Optimize queries using EXPLAIN ANALYZE when performance matters
- Use window functions appropriately for analytical queries
- Use SQLAlchemy or similar ORM for database abstraction when appropriate

### 7. Data Handling
- Use pandas for data manipulation with clear variable names
- Document data transformations in code comments
- Validate data types and shapes after transformations
- Handle missing values explicitly (document the strategy)
- Use `df.info()` and `df.describe()` for initial data exploration
- Set random seeds for reproducibility (`np.random.seed(42)`)
- Use `polars` for large datasets when performance is critical

### 8. Machine Learning Standards
- Split data into train/validation/test sets (e.g., 60/20/20 or 70/15/15)
- Use scikit-learn pipelines for preprocessing + model
- Document hyperparameters and their rationale
- Implement cross-validation for model evaluation
- Track metrics (accuracy, precision, recall, F1, ROC-AUC as appropriate)
- Save models using `joblib` or `pickle` with version tracking
- Document feature importance and model interpretability
- Use MLflow or similar for experiment tracking in production projects

### 9. Testing Requirements
- Write unit tests using pytest for all critical functions
- Use assertions to validate function outputs
- Test edge cases and error conditions
- Aim for >80% code coverage on production code
- Name test files as `test_*.py` and test functions as `test_*`
- Use pytest fixtures for reusable test setup
- Add tests to `tests/` directory mirroring `src/` structure

### 10. Documentation
- Every module should have a module-level docstring
- Functions should explain: purpose, parameters, return values, exceptions
- Update README.md with setup instructions and usage examples
- Add inline comments for complex logic (not obvious code)
- Document API endpoints with request/response examples
- Use docstrings compatible with Sphinx or MkDocs for API documentation

### 11. Git & Version Control
- Write meaningful commit messages (present tense, imperative mood)
- Create feature branches for new functionality
- Keep commits atomic and focused
- Use `.gitignore` for: `__pycache__/`, `*.pyc`, `.env`, `.venv/`, `.DS_Store`, `data/`, `*.egg-info/`, `dist/`, `build/`, `*.pyo`, `*.pyd`, `.mypy_cache/`, `.pytest_cache/`, `htmlcov/`, `.coverage`, `uv.lock` (optional, but recommended to commit)

### 12. Security & Privacy
- Never hardcode API keys, passwords, or credentials
- Use environment variables for all sensitive data
- Scan for secrets before committing code (use `gitleaks` or similar)
- Use `.gitignore` for sensitive files
- Validate and sanitize all external inputs
- Use `secrets` module or environment variables for sensitive data

### 13. Performance Optimization
- Use vectorized operations instead of loops (numpy/pandas/polars)
- Profile code with `cProfile`, `line_profiler`, or `uv run python -m cProfile` before optimizing
- Use appropriate data structures (sets for lookups, dicts for mappings)
- Implement caching for expensive operations (`functools.lru_cache`)
- Use generators for large datasets to manage memory
- Consider `numba` or `cython` for CPU-intensive operations

### 14. Communication Style
- Explain your reasoning before making changes
- Ask clarifying questions when requirements are ambiguous
- Present multiple approaches when trade-offs exist
- Highlight potential risks or side effects
- Provide code examples with explanations
- Be concise but thorough

### 15. File Operations
- Always show a diff before editing any file
- Read the file first to understand existing patterns
- Match existing code style and conventions
- Backup critical files before major changes
- Confirm before deleting or renaming files
- Use `uv run` for all Python file operations

### 16. Terminal Commands
- Explain what each command will do before executing
- Use safe commands (add `--dry-run` when available)
- Check command output for errors
- Use `uv add` and `uv sync` for dependency management
- Use `uv run <command>` for all Python-related commands
- Never use `pip install` directly; always go through uv

## Workflow Preferences

### For New Features:
1. Explore existing codebase structure
2. Clarify requirements and constraints
3. Create detailed plan in `plans/feature_name.md`
4. Review plan together
5. Implement in small, testable increments
6. Write tests alongside implementation
7. Update documentation and README

### For Bug Fixes:
1. Reproduce the issue
2. Identify root cause through code exploration
3. Propose fix strategy
4. Implement minimal change to resolve
5. Add test case to prevent regression
6. Verify no side effects

### For Code Reviews:
1. Check for logic errors and edge cases
2. Verify error handling is adequate
3. Ensure code follows project conventions
4. Look for performance bottlenecks
5. Suggest refactoring opportunities
6. Validate test coverage

## Tools & Commands to Use

### uv Commands
- `uv init <project_name>` - Initialize new project
- `uv venv` - Create virtual environment
- `uv add <package>` - Add dependency
- `uv remove <package>` - Remove dependency
- `uv sync` - Sync dependencies from pyproject.toml
- `uv run <command>` - Run command in project environment
- `uv export > requirements.txt` - Export dependencies to requirements.txt
- `uv tree` - Show dependency tree
- `uv outdated` - Check for outdated packages

### Development Commands
- `uv run python -m pytest tests/` - Run tests
- `uv run python -m pytest tests/ -v --cov=src` - Run tests with coverage
- `uv run python -m black .` - Format code
- `uv run python -m flake8 .` - Lint code
- `uv run python -m mypy .` - Type check
- `uv run python -m isort .` - Sort imports
- `uv run ipython` - Start interactive Python shell
- `uv run jupyter notebook` - Start Jupyter (if installed)

### Environment Commands
- `source .venv/bin/activate` - Activate venv (MacOS/Linux)
- `.venv\Scripts\activate` - Activate venv (Windows)
- `uv run python -c "import sys; print(sys.executable)"` - Verify environment

## Response Format
- Use markdown for clear structure
- Include code blocks with syntax highlighting
- Use tables for comparisons
- Break complex tasks into numbered steps
- Cite sources when referencing external documentation
- Keep responses concise but complete

## Special Considerations for Data Science Projects

### Data Pipeline Standards
- Use modular design: separate data loading, transformation, and validation
- Implement data validation with `pydantic` or `pandera` for schema validation
- Log data quality metrics and anomalies
- Use incremental processing for large datasets
- Implement checkpointing for long-running pipelines

### Experimentation Best Practices
- Track experiments with MLflow, Weights & Biases, or simple logging
- Save model artifacts with metadata (timestamp, hyperparameters, metrics)
- Use configuration files (YAML/JSON) for experiment parameters
- Implement reproducibility: fix random seeds, log dependencies
- Version control notebooks and scripts separately

### Production Readiness
- Containerize with Docker when deploying
- Use CI/CD pipelines for automated testing
- Implement monitoring and alerting for production models
- Document API contracts and data schemas
- Use feature stores for consistent feature engineering

CRITICAL: You are running on a local inference engine. 
You must ALWAYS perfectly format your tool calls using exact, un-nested XML tags. 
Never omit a closing tag (e.g., ALWAYS match <read_file> with </read_file>).
Do not add conversational fluff outside or inside the tool tags.
