from enum import Enum


class PolicyStatus(str, Enum):
    crawl_allowed = "crawl_allowed"
    partner_required = "partner_required"
    manual_only = "manual_only"
    unknown = "unknown"


class TaskType(str, Enum):
    SearchTask = "SearchTask"
    MapTask = "MapTask"
    CrawlTask = "CrawlTask"
    ScrapeTask = "ScrapeTask"
    ImportTask = "ImportTask"


class EvidenceKind(str, Enum):
    text_span = "text_span"
    image_region = "image_region"
