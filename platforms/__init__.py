from platforms.naukri import NaukriPlatform
from platforms.instahyre import InstahyrePlatform
from platforms.linkedin import LinkedInPlatform
from platforms.indeed import IndeedPlatform
from platforms.glassdoor import GlassdoorPlatform
from platforms.foundit import FounditPlatform
from platforms.timesjobs import TimesJobsPlatform
from platforms.shine import ShinePlatform
from platforms.iimjobs import IimjobsPlatform
from platforms.wellfound import WellfoundPlatform
from platforms.cutshort import CutshortPlatform
from platforms.hirist import HiristPlatform
from platforms.internshala import IntershalaPlatform

ALL_PLATFORMS = [
    NaukriPlatform,
    InstahyrePlatform,
    LinkedInPlatform,
    IndeedPlatform,
    GlassdoorPlatform,
    FounditPlatform,
    TimesJobsPlatform,
    ShinePlatform,
    IimjobsPlatform,
    WellfoundPlatform,
    CutshortPlatform,
    HiristPlatform,
    IntershalaPlatform,
]

PLATFORM_MAP = {cls.name: cls for cls in ALL_PLATFORMS}
