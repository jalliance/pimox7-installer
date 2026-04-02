from .github_forks import GitHubForksSource
from .git_mirrors import GitMirrorsSource
from .wayback import WaybackSource
from .software_heritage import SoftwareHeritageSource
from .package_registries import PackageRegistriesSource
from .google_cache import GoogleCacheSource

ALL_SOURCES = [
    GitHubForksSource(),
    GitMirrorsSource(),
    WaybackSource(),
    SoftwareHeritageSource(),
    PackageRegistriesSource(),
    GoogleCacheSource(),
]

SOURCE_NAMES = {s.name: s for s in ALL_SOURCES}
