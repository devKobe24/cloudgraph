"""`awsgraph design` — open the standalone designer in a browser.

No localhost server: the design file and the pricing catalog are embedded into a
temporary copy of the bundled designer, which is then opened with a file URL
(guide section 14.2).
"""

from __future__ import annotations

import json
import re
import tempfile
import webbrowser
from importlib import resources
from pathlib import Path

from .export import json_for_html
from .pricing import PricingCatalog
from .schema import Architecture

DATA_ELEMENT_ID = "awsgraph-design"

# Target the data element by id rather than replacing a bare token: the bundled
# JavaScript also contains the token as a string literal (it uses it to detect
# being opened without the CLI), and replacing that broke the bundle.
DATA_BLOCK = re.compile(
    r'(<script[^>]*id="' + DATA_ELEMENT_ID + r'"[^>]*>)(.*?)(</script>)',
    re.DOTALL,
)


class DesignerAssetError(Exception):
    """The bundled designer is missing or was built without its data element."""


def _asset():
    return resources.files("awsgraph") / "assets" / "designer.html"


def render(architecture: Architecture, catalog: PricingCatalog) -> str:
    asset = _asset()
    if not asset.is_file():
        raise DesignerAssetError(
            "this build has no designer asset. Reinstall awsgraph, or build it "
            "from source with `python -m tools.build_web`."
        )
    template = asset.read_text(encoding="utf-8")
    if not DATA_BLOCK.search(template):
        raise DesignerAssetError(
            "the bundled designer has no data element; rebuild it with `python -m tools.build_web`."
        )
    payload = {
        "architecture": json.loads(architecture.model_dump_json()),
        "catalog": {
            "catalog_id": catalog.catalog_id,
            "region": catalog.region,
            "currency": catalog.currency,
            "rates": dict(catalog.rates),
        },
    }
    embedded = json_for_html(payload)
    return DATA_BLOCK.sub(lambda m: m.group(1) + embedded + m.group(3), template, count=1)


def write_temp(html: str, name: str) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="awsgraph-design-"))
    path = directory / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    return path


def open_designer(
    architecture: Architecture,
    catalog: PricingCatalog,
    *,
    open_browser: bool = True,
) -> Path:
    path = write_temp(render(architecture, catalog), "designer")
    if open_browser:
        webbrowser.open(path.as_uri())
    return path
