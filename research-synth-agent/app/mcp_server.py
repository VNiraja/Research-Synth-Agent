"""
Research Synth MCP Server — FastMCP HTTP/SSE transport (Windows compatible)
Runs on http://localhost:8090

Start with:  uv run python -m app.mcp_server

Tools:
  search_arxiv               — search arXiv by keyword
  search_semantic_scholar    — search Semantic Scholar
  extract_key_findings       — extract key sentences from abstracts
  format_citation            — format APA / MLA / Chicago refs
  detect_duplicate_citations — deduplicate papers by title similarity
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

from mcp.server.fastmcp import FastMCP

MCP_PORT = 8090
mcp = FastMCP("research-synth-mcp", host="127.0.0.1", port=MCP_PORT)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: search_arxiv
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def search_arxiv(query: str, max_results: int = 5) -> str:
    """Search arXiv for academic papers matching a query.

    Args:
        query: Research topic or keywords to search for.
        max_results: Maximum number of papers to return (1-10).

    Returns:
        JSON string with papers list and total_found count.
    """
    max_results = min(max(1, max_results), 10)
    try:
        encoded_query = urllib.parse.quote(query)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded_query}"
            f"&start=0&max_results={max_results}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchSynthAgent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read().decode("utf-8")

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            id_el = entry.find("atom:id", ns)
            published_el = entry.find("atom:published", ns)
            authors = [
                a.find("atom:name", ns).text
                for a in entry.findall("atom:author", ns)
                if a.find("atom:name", ns) is not None
            ]
            papers.append({
                "title": (title_el.text or "").strip().replace("\n", " "),
                "abstract": (summary_el.text or "").strip().replace("\n", " ")[:500],
                "authors": authors[:5],
                "year": (published_el.text or "")[:4],
                "url": (id_el.text or "").replace("abs", "pdf"),
                "source": "arxiv",
            })
        
        print("Sleeping 25 seconds to respect Gemini rate limits...")
        time.sleep(25)
        return json.dumps({"papers": papers, "total_found": len(papers), "query": query})
    except Exception as exc:
        return json.dumps({"error": str(exc), "papers": [], "query": query})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: search_semantic_scholar
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def search_semantic_scholar(query: str, max_results: int = 5) -> str:
    """Search Semantic Scholar for academic papers.

    Args:
        query: Research topic or keywords to search for.
        max_results: Maximum number of papers to return (1-10).

    Returns:
        JSON string with papers list and total_found count.
    """
    max_results = min(max(1, max_results), 10)
    try:
        encoded_query = urllib.parse.quote(query)
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={encoded_query}&limit={max_results}"
            f"&fields=title,authors,year,abstract,url,externalIds"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ResearchSynthAgent/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        papers = []
        for p in data.get("data", []):
            paper_id = p.get("paperId", "")
            papers.append({
                "title": p.get("title", ""),
                "abstract": (p.get("abstract") or "")[:500],
                "authors": [a.get("name", "") for a in p.get("authors", [])[:5]],
                "year": str(p.get("year", "")),
                "url": f"https://www.semanticscholar.org/paper/{paper_id}",
                "source": "semantic_scholar",
            })
        
        print("Sleeping 25 seconds to respect Gemini rate limits...")
        time.sleep(25)
        return json.dumps({"papers": papers, "total_found": len(papers), "query": query})
    except Exception as exc:
        return json.dumps({"error": str(exc), "papers": [], "query": query})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: extract_key_findings
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def extract_key_findings(papers_json: str) -> str:
    """Extract key finding sentences from a list of paper abstracts.

    Args:
        papers_json: JSON string containing a list of paper objects with
                     title, abstract, authors, year, url fields.

    Returns:
        JSON string with extracted key findings per paper.
    """
    try:
        papers = json.loads(papers_json) if isinstance(papers_json, str) else papers_json
    except Exception:
        return json.dumps({"error": "Invalid papers_json", "findings": []})

    result_keywords = [
        "we show", "we find", "we demonstrate", "results show",
        "we propose", "our method", "we achieve", "outperforms",
        "significantly", "novel", "state-of-the-art", "improvement",
    ]
    findings = []
    for paper in papers:
        abstract = paper.get("abstract", "")
        sentences = re.split(r"(?<=[.!?])\s+", abstract)
        key_sentences = [s.strip() for s in sentences if any(kw in s.lower() for kw in result_keywords)]
        if not key_sentences and len(sentences) >= 2:
            key_sentences = sentences[-2:]
        findings.append({
            "paper_title": paper.get("title", ""),
            "key_findings": key_sentences[:3],
            "authors": paper.get("authors", []),
            "year": paper.get("year", ""),
            "url": paper.get("url", ""),
        })
    return json.dumps({"findings": findings})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 4: format_citation
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def format_citation(papers_json: str) -> str:
    """Format papers as APA, MLA, and Chicago citations.

    Args:
        papers_json: JSON string with list of papers (title, authors, year, url, source).

    Returns:
        JSON string with apa, mla, chicago citation lists.
    """
    try:
        papers = json.loads(papers_json) if isinstance(papers_json, str) else papers_json
    except Exception:
        return json.dumps({"error": "Invalid papers_json", "citations": []})

    def apa_authors(auths):
        if not auths:
            return "Unknown Author"
        parts = []
        for a in auths[:6]:
            name_parts = a.strip().split()
            if len(name_parts) >= 2:
                last = name_parts[-1]
                initials = ". ".join(n[0] for n in name_parts[:-1]) + "."
                parts.append(f"{last}, {initials}")
            else:
                parts.append(a)
        return ", ".join(parts) + (" et al." if len(auths) > 6 else "")

    def mla_first(auths):
        return auths[0] if auths else "Unknown"

    formatted = []
    for i, paper in enumerate(papers, start=1):
        title = paper.get("title", "Unknown Title")
        authors = paper.get("authors", [])
        year = paper.get("year", "n.d.")
        url = paper.get("url", "")
        source = paper.get("source", "").replace("_", " ").title()
        first = mla_first(authors)
        et_al = ", et al." if len(authors) > 1 else ""
        formatted.append({
            "ref_id": i,
            "apa": f"[{i}] {apa_authors(authors)} ({year}). {title}. {source}. {url}",
            "mla": f'[{i}] {first}{et_al}. "{title}." {source}, {year}. {url}',
            "chicago": f'[{i}] {first}{et_al}. "{title}." {source} ({year}). {url}',
        })

    apa = [c["apa"] for c in formatted]
    mla = [c["mla"] for c in formatted]
    chicago = [c["chicago"] for c in formatted]
    return json.dumps({
        "apa": apa, "mla": mla, "chicago": chicago,
        "reference_count": len(formatted), "duplicates_removed": 0,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Tool 5: detect_duplicate_citations
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def detect_duplicate_citations(papers_json: str, similarity_threshold: float = 0.85) -> str:
    """Detect and remove duplicate papers by title similarity.

    Args:
        papers_json: JSON string with list of paper objects.
        similarity_threshold: Ratio 0.0–1.0 above which papers are duplicates.

    Returns:
        JSON string with unique_papers, duplicates info, counts.
    """
    try:
        papers = json.loads(papers_json) if isinstance(papers_json, str) else papers_json
    except Exception:
        return json.dumps({"error": "Invalid papers_json"})

    duplicates = []
    seen = set()
    unique = []
    for i, p1 in enumerate(papers):
        if i in seen:
            continue
        for j, p2 in enumerate(papers):
            if i >= j or j in seen:
                continue
            ratio = SequenceMatcher(None, p1.get("title", "").lower(), p2.get("title", "").lower()).ratio()
            if ratio >= similarity_threshold:
                duplicates.append({"paper_a": p1.get("title"), "paper_b": p2.get("title"), "similarity": round(ratio, 3)})
                seen.add(j)
        unique.append(p1)

    return json.dumps({
        "original_count": len(papers),
        "unique_count": len(unique),
        "duplicates_found": len(duplicates),
        "duplicates": duplicates,
        "unique_papers": unique,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — HTTP/SSE server on port 8090
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # DuckDuckGo Fallback Tool
    @mcp.tool()
    def search_duckduckgo(query: str, max_results: int = 5) -> str:
        """Search the web for general topics or recent news using DuckDuckGo when academic databases fail."""
        try:
            from ddgs import DDGS
            results = DDGS().text(query, max_results=max_results)
            if not results:
                return "No web results found."
            
            output = [f"DuckDuckGo Search Results for: {query}"]
            for r in results:
                output.append(f"Title: {r.get('title')}\nLink: {r.get('href')}\nSnippet: {r.get('body')}\n")
            
            print("Sleeping 25 seconds to respect Gemini rate limits...")
            time.sleep(25)
            return "\n".join(output)
        except Exception as e:
            return f"DuckDuckGo search error: {str(e)}"
    
    # Run the FastMCP server
    print(f"Starting Research Synth MCP server on http://127.0.0.1:{MCP_PORT}")
    print(f"SSE endpoint: http://127.0.0.1:{MCP_PORT}/sse")
    mcp.run(transport="sse")
