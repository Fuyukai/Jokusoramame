"""
The global web template renderer.

The environment defined here is global and can be used by all routes.
"""
from jinja2 import Environment, FileSystemLoader, select_autoescape
from kyoukai.asphalt import HTTPRequestContext

env = Environment(
    loader=FileSystemLoader("site/templates"),
    autoescape=select_autoescape(['html', 'xml']),
    enable_async=True
)


async def render_template(name: str, ctx: HTTPRequestContext, **kwargs):
    """
    Renders a template.
    
    :param name: The name/path of the template. 
    :param ctx: The HTTPRequestContext of the template.
    :param kwargs: Any additional keyword arguments to pass in.
    """
    tmpl = env.get_template(name)

    expanded = {
        "ctx": ctx,
        "request": ctx.request,
        "bot": ctx.bot,
        **kwargs
    }

    try:
        rendered = await tmpl.render_async(**expanded)
    except RuntimeError:  # 3.5
        rendered = tmpl.render(**expanded)

    return rendered
