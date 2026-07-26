from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class PromptLoader:
    """Load and render Jinja2 prompt templates from config/prompts/.

    Provides a simple interface for loading prompt templates and
    rendering them with context variables. Templates live under
    config/prompts/ as .j2 files — separate from code so prompt
    engineering does not require code deployments.

    Usage::

        loader = PromptLoader()
        prompt = loader.render("assess_cpu.j2", language="vi")
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        if template_dir is None:
            template_dir = (
                Path(__file__).resolve().parent.parent.parent.parent
                / "config"
                / "prompts"
            )
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
        )

    def render(self, template_name: str, **context: object) -> str:
        """Render a Jinja2 prompt template with the given context.

        Args:
            template_name: The .j2 filename (e.g. 'assess_cpu.j2').
            **context: Variables passed to the Jinja2 template.

        Returns:
            The rendered prompt string.
        """
        template = self._env.get_template(template_name)
        return template.render(**context)

    def render_raw(self, template_name: str) -> str:
        """Render a template with no context variables.

        Convenience method for templates that are purely static text.

        Args:
            template_name: The .j2 filename.

        Returns:
            The rendered prompt string.
        """
        template = self._env.get_template(template_name)
        return template.render()
