"""Built-in ruleset of reclaimable developer artifacts.

Each rule names a directory that, when found, can be safely deleted to reclaim
disk space. Rules are tagged with the ecosystem they belong to and a short
human description. The ruleset is intentionally conservative: every entry is a
regenerable build/dependency cache, never source code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Rule:
    """A single reclaimable-directory rule.

    Attributes:
        dir_name: Exact directory basename to match (case-insensitive on
            Windows/macOS semantics are handled by the caller; we match the
            literal name).
        ecosystem: Short tag for the toolchain this artifact belongs to.
        description: Human-readable note shown in listings.
        marker_files: If non-empty, the rule only matches when at least one of
            these sibling files exists next to the candidate directory. This
            avoids false positives for generic names like ``build`` or
            ``dist`` that also appear in non-dev trees.
    """

    dir_name: str
    ecosystem: str
    description: str
    marker_files: tuple[str, ...] = field(default_factory=tuple)


# The canonical ruleset. Ordering is cosmetic; matching is by exact basename.
RULES: tuple[Rule, ...] = (
    # --- JavaScript / TypeScript ---
    Rule("node_modules", "node", "npm/yarn/pnpm installed dependencies"),
    Rule(".next", "node", "Next.js build output", ("package.json",)),
    Rule(".nuxt", "node", "Nuxt build output", ("package.json",)),
    Rule(".turbo", "node", "Turborepo cache", ("package.json",)),
    Rule(".parcel-cache", "node", "Parcel bundler cache", ("package.json",)),
    Rule(".svelte-kit", "node", "SvelteKit build output", ("package.json",)),
    Rule(".angular", "node", "Angular CLI cache", ("package.json",)),
    Rule("bower_components", "node", "Bower installed dependencies"),
    # --- Python ---
    Rule(".venv", "python", "Python virtual environment"),
    Rule("venv", "python", "Python virtual environment"),
    Rule("env", "python", "Python virtual environment", ("pyvenv.cfg",)),
    Rule("__pycache__", "python", "Python bytecode cache"),
    Rule(".pytest_cache", "python", "pytest cache"),
    Rule(".mypy_cache", "python", "mypy type-check cache"),
    Rule(".ruff_cache", "python", "Ruff linter cache"),
    Rule(".tox", "python", "tox environments"),
    Rule(".eggs", "python", "setuptools build eggs"),
    # --- Rust ---
    Rule("target", "rust", "Cargo build output", ("Cargo.toml",)),
    # --- Java / JVM / Gradle / Maven ---
    Rule(".gradle", "jvm", "Gradle cache"),
    Rule("build", "jvm", "Gradle/other build output",
         ("build.gradle", "build.gradle.kts", "pom.xml")),
    # --- Apple / Xcode ---
    Rule("DerivedData", "apple", "Xcode derived data"),
    Rule("Pods", "apple", "CocoaPods installed dependencies", ("Podfile",)),
    # --- Go ---
    Rule("vendor", "go", "Go vendored dependencies", ("go.mod",)),
    # --- PHP ---
    Rule("vendor", "php", "Composer dependencies", ("composer.json",)),
    # --- .NET ---
    Rule("bin", "dotnet", ".NET build output",
         ("*.csproj", "*.fsproj", "*.sln")),
    Rule("obj", "dotnet", ".NET intermediate output",
         ("*.csproj", "*.fsproj", "*.sln")),
    # --- Generic build/dist (guarded by common manifests) ---
    Rule("dist", "generic", "Generic build/dist output",
         ("package.json", "setup.py", "pyproject.toml")),
    # --- Misc caches ---
    Rule(".cache", "generic", "Generic tool cache", ("package.json",)),
    Rule(".terraform", "infra", "Terraform provider/module cache"),
)


def ecosystems() -> tuple[str, ...]:
    """Return the sorted set of distinct ecosystems in the ruleset."""
    return tuple(sorted({r.ecosystem for r in RULES}))


def rule_names() -> frozenset[str]:
    """Return the set of directory basenames that any rule matches."""
    return frozenset(r.dir_name for r in RULES)


def rules_for_name(name: str) -> tuple[Rule, ...]:
    """Return all rules whose ``dir_name`` equals ``name`` (exact match)."""
    return tuple(r for r in RULES if r.dir_name == name)
