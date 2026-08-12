"""
Test all scrapers and report what data they return.
Run from the project root: python test_scrapers.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_scraper(name, module_path, filters):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    try:
        import importlib
        mod = importlib.import_module(module_path)
        results = mod.scrape(filters)
        print(f"✅ SUCCESS: {len(results)} results")
        for i, r in enumerate(results[:3]):
            print(f"  [{i+1}] {r.get('title','?')[:50]} @ {r.get('organization','?')[:30]}")
            print(f"       type={r.get('type')} | deadline={r.get('deadline')} | source={r.get('source')}")
        return results
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    filters = {"type": "all", "domain": "general", "location": "all"}
    
    all_results = []
    
    r = test_scraper("Remotive (Jobs API)", "backend.scraper.remotive", filters)
    all_results.extend(r)
    
    d = test_scraper("Devpost (Hackathons)", "backend.scraper.devpost", filters)
    all_results.extend(d)
    
    u = test_scraper("Unstop (Competitions)", "backend.scraper.unstop", filters)
    all_results.extend(u)
    
    i = test_scraper("Internshala (Internships)", "backend.scraper.internshala", filters)
    all_results.extend(i)
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(all_results)} opportunities across all sources")
    print(f"  Remotive: {len(r)}")
    print(f"  Devpost:  {len(d)}")
    print(f"  Unstop:   {len(u)}")
    print(f"  Internshala: {len(i)}")
    print(f"{'='*60}")
