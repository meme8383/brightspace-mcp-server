"""
Brightspace MCP Server - Playwright-based web scraping for Purdue University
"""

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
import time
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class Course:
    """Data class for course information"""
    name: str
    code: str
    instructor: str
    url: str


@dataclass
class Assignment:
    title: str
    due_date: str
    status: str  # "Submitted", "Not Submitted", etc.
    score: str   # "100 / 100 - 100 %" or "- / 100 -"
    feedback: str  # "Read", "Unread", ""
    category: str
    url: str


@dataclass
class GradeItem:
    name: str
    points: str       # "100 / 100"
    weight: str       # "1.2 / 1.2"
    grade: str        # "100 %"
    category: str


@dataclass
class Announcement:
    title: str
    date: str


@dataclass
class Quiz:
    name: str
    due_date: str
    available: str
    status: str     # "Feedback: On Attempt", etc.
    attempts: str   # "1 / Unlimited"


@dataclass
class ContentModule:
    name: str
    items: List[str]  # topic names within the module


@dataclass
class ContentItem:
    name: str
    item_type: str   # "Quiz", "File", "C File", "PDF document", etc.
    url: str
    dates: str       # "Starts ..., Ends ..." or ""


class BrightspaceScraper:
    """Main class for scraping Purdue Brightspace data"""

    COOKIE_FILE = Path(__file__).parent / ".cookies.json"

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self):
        """Context manager entry"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()

    # ── cookie persistence ──────────────────────────────────────────

    def save_cookies(self):
        """Save browser cookies to disk for later headless reuse."""
        cookies = self.context.cookies()
        self.COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"Saved {len(cookies)} cookies to {self.COOKIE_FILE}")

    def load_cookies(self) -> bool:
        """Load saved cookies into the browser context.
        Returns True if cookies were loaded, False otherwise."""
        if not self.COOKIE_FILE.exists():
            return False
        try:
            cookies = json.loads(self.COOKIE_FILE.read_text())
            self.context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} cookies from cache")
            return True
        except (json.JSONDecodeError, Exception) as e:
            print(f"Failed to load cookies: {e}")
            return False

    def is_logged_in(self) -> bool:
        """Check if the current session is authenticated."""
        try:
            self.page.goto("https://purdue.brightspace.com/d2l/home", wait_until="domcontentloaded", timeout=15000)
            self.page.wait_for_load_state("networkidle", timeout=10000)
            return "/d2l/home" in self.page.url and "/login" not in self.page.url
        except Exception:
            return False

    def login_with_cookies(self) -> bool:
        """Attempt to restore a session from cached cookies.
        Returns True if the cached session is still valid."""
        if not self.load_cookies():
            return False
        print("Checking if cached session is still valid...")
        if self.is_logged_in():
            print("Session restored from cookies!")
            return True
        print("Cached cookies expired.")
        return False
    
    def login(self, username: str, password: str) -> bool:
        """
        Login to Purdue Brightspace with Duo Mobile 2FA
        
        Args:
            username: Purdue Career Account username
            password: Purdue Career Account password
            
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            # Navigate to Purdue Brightspace login
            print("Navigating to Purdue Brightspace...")
            self.page.goto("https://purdue.brightspace.com")
            
            # Wait for page to load
            self.page.wait_for_load_state("networkidle")
            
            # Click on Purdue West Lafayette / Indianapolis button
            print("Looking for Purdue institution selector...")
            try:
                purdue_button = self.page.wait_for_selector("text=Purdue West Lafayette / Indianapolis", timeout=5000)
                if purdue_button:
                    print("Clicking Purdue West Lafayette button...")
                    purdue_button.click()
                    self.page.wait_for_load_state("networkidle")
            except Exception as e:
                print(f"Note: Institution selector not found or not needed: {e}")
            
            # Wait for login form to load
            print("Waiting for login form...")
            self.page.wait_for_selector("#username", timeout=10000)
            
            # Fill in credentials
            print("Entering credentials...")
            self.page.fill("#username", username)
            self.page.fill("#password", password)
            
            # Click login button
            print("Clicking login button...")
            self.page.click("button[type='submit']")
            
            # Wait for Duo Mobile prompt
            print("Waiting for Duo Mobile authentication...")
            print("Please approve the login request on your Duo Mobile app...")
            
            # Wait for successful authentication by checking for Brightspace homepage
            try:
                # Wait for navigation away from Duo page to Brightspace
                self.page.wait_for_function(
                    "() => window.location.href.includes('/d2l/home')",
                    timeout=60000
                )
                print("Duo Mobile authentication successful!")
                self.save_cookies()
                return True
            except Exception as e:
                print(f"Authentication failed or timed out: {e}")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def get_courses(self) -> List[Course]:
        """
        Scrape list of enrolled courses
        
        Returns:
            List[Course]: List of course objects
        """
        try:
            # Navigate to home page
            print("Navigating to homepage...")
            self.page.goto("https://purdue.brightspace.com/d2l/home")
            
            # Wait for the My Courses widget to load (it's a web component)
            print("Waiting for My Courses widget to load...")
            self.page.wait_for_selector("d2l-my-courses", timeout=10000)
            
            # Wait a bit more for the courses to render inside the component
            time.sleep(3)
            
            # The courses are loaded dynamically, so we need to wait for them
            # Try multiple possible selectors based on the actual HTML structure
            course_selectors = [
                "d2l-enrollment-card .d2l-card-container",  # Main course containers
                ".d2l-card-container",  # Course card containers
                "d2l-enrollment-card a[href*='/d2l/home/']",  # Course links
                "a[href*='/d2l/home/']",  # Any course links
            ]
            
            courses = []
            for selector in course_selectors:
                print(f"Trying selector: {selector}")
                course_elements = self.page.query_selector_all(selector)
                
                if course_elements:
                    print(f"Found {len(course_elements)} course elements with {selector}")
                    
                    for element in course_elements:
                        try:
                            # If this is a link element, use it directly
                            if element.evaluate("el => el.tagName.toLowerCase()") == "a":
                                link_element = element
                            else:
                                # Otherwise, look for a link inside this element
                                link_element = element.query_selector("a[href*='/d2l/home/']")
                            
                            if not link_element:
                                continue
                            
                            # Get course URL
                            url = link_element.get_attribute("href")
                            if not url:
                                continue
                            
                            # Get course name from the span inside the link
                            name_span = link_element.query_selector(".d2l-card-link-text")
                            if name_span:
                                name = name_span.text_content().strip()
                            else:
                                # Fallback: get from link text or title
                                name = (
                                    link_element.get_attribute("title") or
                                    link_element.get_attribute("aria-label") or
                                    link_element.text_content()
                                )
                                if name:
                                    name = name.strip()
                            
                            # Extract course code from name
                            course_code = self._extract_course_code(name) if name else "Unknown"
                            
                            if name and name != "":
                                courses.append(Course(
                                    name=name,
                                    code=course_code,
                                    instructor="",
                                    url=url
                                ))
                                print(f"Found course: {name} ({course_code})")
                        except Exception as e:
                            print(f"Error extracting course from element: {e}")
                            continue
                    
                    # If we found courses, don't try other selectors
                    if courses:
                        break
            
            # If no courses found with any selector, take a screenshot for debugging
            if not courses:
                print("No courses found! Taking screenshot...")
                self.page.screenshot(path="homepage_debug.png")
                print("Screenshot saved as homepage_debug.png")
                print("Printing page HTML to debug...")
                # Get the inner HTML of the my-courses widget
                my_courses = self.page.query_selector("d2l-my-courses")
                if my_courses:
                    print(f"My Courses widget found, but no course elements inside")
                else:
                    print("My Courses widget not found!")
            
            return courses
            
        except Exception as e:
            print(f"Error getting courses: {e}")
            self.page.screenshot(path="error_getting_courses.png")
            return []
    
    def _course_id(self, course_url: str) -> str:
        """Extract numeric course ID from a course URL like /d2l/home/1579176."""
        import re
        m = re.search(r'/(\d+)$', course_url.rstrip('/'))
        return m.group(1) if m else course_url

    def get_assignments(self, course_url: str) -> List[Assignment]:
        """Scrape assignments (Dropbox folders) for a course."""
        import re
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/lms/dropbox/user/folders_list.d2l?ou={cid}"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)
            table = (
                self.page.query_selector('table[summary="List of assignments for this course"]')
                or self.page.query_selector("table.d2l-table.d2l-grid")
            )
            if not table:
                return []

            rows = table.query_selector_all("tr")
            assignments = []
            category = ""

            for row in rows[1:]:  # skip header
                cls = row.get_attribute("class") or ""

                # Category header rows
                if "d_ggl" in cls or "d_dbold" in cls:
                    category = (row.text_content() or "").strip()
                    continue

                # Assignment rows have a <TH> as the first cell with the title.
                # File sub-rows start with <TD> — skip those.
                first_cell = row.query_selector("th")
                if not first_cell:
                    continue

                raw = (first_cell.text_content() or "").strip()
                title, due_date = raw, ""
                dm = re.search(r'^(.+?)(?:Due on |Due )(.*?)(?:Available|$)', raw, re.S)
                if dm:
                    title = dm.group(1).strip()
                    due_date = dm.group(2).strip()

                # Collect all <td> cells after the <th>
                tds = row.query_selector_all("td")

                # Rows have variable cell counts:
                #   Submitted (4 total): [th:title, td:submission, td:score, td:feedback]
                #   In-progress (8 total): [th:title, td:file, td, td, td, td:status, td:score, td]
                #   Unsubmitted (4 total): [th:title, td:status, td:score, td]
                status = score = feedback = ""
                all_td_text = [(td.text_content() or "").strip() for td in tds]

                # Find status, score, feedback from td texts
                for t in all_td_text:
                    if "Not Submitted" in t:
                        status = "Not Submitted"
                    elif "Submission" in t:
                        status = "Submitted"
                    elif re.match(r'^-?\s*/\s*\d+|^\d+\s*/\s*\d+', t):
                        score = t
                    elif t.startswith("Feedback:"):
                        feedback = t

                if not status and score:
                    status = "Graded"

                link = row.query_selector('a[href*="folders_history"]')

                assignments.append(Assignment(
                    title=title,
                    due_date=due_date,
                    status=status,
                    score=score,
                    feedback=feedback,
                    category=category,
                    url=(link.get_attribute("href") or "") if link else "",
                ))

            return assignments
        except Exception as e:
            print(f"Error getting assignments: {e}")
            return []

    def get_grades(self, course_url: str) -> List[GradeItem]:
        """Scrape grade items for a course."""
        import re
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/lms/grades/my_grades/main.d2l?ou={cid}"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)
            table = (
                self.page.query_selector('table[summary*="grade"]')
                or self.page.query_selector("table.d2l-table.d2l-grid")
            )
            if not table:
                return []

            # Only get direct child rows of the main table (not nested sub-tables)
            rows = table.query_selector_all(":scope > tbody > tr, :scope > tr")
            grades = []
            category = ""

            for row in rows[1:]:  # skip header
                cls = row.get_attribute("class") or ""

                # Only use direct <td>/<th> children — not cells inside nested tables
                cells = row.query_selector_all(":scope > td, :scope > th")
                if not cells:
                    continue

                # Category rows have d_ggl in class
                if "d_ggl" in cls:
                    category = (cells[0].text_content() or "").strip()
                    continue

                # Grade item rows: [spacer_td, name_td, points_td, weight_td, grade_td, comments_td]
                # Direct text of each cell (not including nested table content)
                cell_texts = []
                for c in cells:
                    # Get only the direct text, excluding nested tables
                    nested = c.query_selector("table")
                    if nested:
                        # Remove nested table text by getting inner text minus nested
                        full = (c.text_content() or "").strip()
                        nested_text = (nested.text_content() or "").strip()
                        direct = full.replace(nested_text, "").strip()
                        cell_texts.append(direct)
                    else:
                        cell_texts.append((c.text_content() or "").strip())

                # Name is in the second cell (index 1), first cell is indent spacer
                name = cell_texts[1] if len(cell_texts) > 1 else ""
                if not name or name == "":
                    continue

                points = cell_texts[2] if len(cell_texts) > 2 else ""
                weight = cell_texts[3] if len(cell_texts) > 3 else ""
                grade_pct = cell_texts[4] if len(cell_texts) > 4 else ""

                grades.append(GradeItem(
                    name=name,
                    points=points,
                    weight=weight,
                    grade=grade_pct,
                    category=category,
                ))

            return grades
        except Exception as e:
            print(f"Error getting grades: {e}")
            return []

    def get_announcements(self, course_url: str) -> List[Announcement]:
        """Scrape announcements for a course."""
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/lms/news/main.d2l?ou={cid}"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)
            table = self.page.query_selector('table[summary="List of announcements"]')
            if not table:
                return []

            rows = table.query_selector_all("tr")
            announcements = []

            for row in rows[1:]:  # skip header
                cls = row.get_attribute("class") or ""
                if "d_detailsRow" in cls:
                    continue  # skip detail/expand rows
                cells = row.query_selector_all("td, th")
                if len(cells) < 2:
                    continue
                title = " ".join((cells[0].text_content() or "").split())
                date = (cells[1].text_content() or "").strip()
                if title:
                    announcements.append(Announcement(title=title, date=date))

            return announcements
        except Exception as e:
            print(f"Error getting announcements: {e}")
            return []

    def get_quizzes(self, course_url: str) -> List[Quiz]:
        """Scrape quizzes for a course."""
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/lms/quizzing/user/quizzes_list.d2l?ou={cid}"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)

            # Find the table with quiz data (headers: Current Quizzes, Evaluation Status, Attempts)
            table = None
            for t in self.page.query_selector_all("table"):
                rows = t.query_selector_all("tr")
                if len(rows) > 2:
                    table = t
                    break
            if not table:
                return []

            rows = table.query_selector_all("tr")
            quizzes = []

            for row in rows[1:]:  # skip header
                cells = row.query_selector_all("td")
                if len(cells) < 3:
                    continue

                link = row.query_selector("a")
                name = (link.text_content() or "").strip() if link else ""
                if not name:
                    continue

                raw = (cells[0].text_content() or "").strip()
                # Parse "Name Due on <date>Available on <date> until <date>"
                import re
                due_date = available = ""
                dm = re.search(r'Due on (.+?)(?:Available|$)', raw, re.S)
                if dm:
                    due_date = dm.group(1).strip()
                am = re.search(r'Available on (.+?)(?:until|$)', raw, re.S)
                if am:
                    available = am.group(1).strip()

                status = (cells[1].text_content() or "").strip()
                attempts = (cells[2].text_content() or "").strip()

                quizzes.append(Quiz(
                    name=name,
                    due_date=due_date,
                    available=available,
                    status=status,
                    attempts=attempts,
                ))

            return quizzes
        except Exception as e:
            print(f"Error getting quizzes: {e}")
            return []

    def get_content(self, course_url: str) -> List[ContentModule]:
        """Scrape course content modules and their topics."""
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/le/content/{cid}/Home"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)

            modules = []
            module_els = self.page.query_selector_all("li.d2l-le-TreeAccordionItem")
            for mel in module_els:
                label = mel.query_selector(".d2l-textblock")
                name = (label.text_content() or "").strip() if label else ""
                if not name:
                    continue
                modules.append(ContentModule(name=name, items=[]))

            # Get content items (topics) from the currently visible list
            item_els = self.page.query_selector_all(".d2l-datalist-item")
            items_list = []
            for iel in item_els:
                link = iel.query_selector('a[href*="viewContent"]')
                if not link:
                    continue
                iname = (link.text_content() or "").strip()
                tbs = iel.query_selector_all(".d2l-textblock")
                texts = [(t.text_content() or "").strip() for t in tbs]
                item_type = texts[0] if texts else ""
                dates = " ".join(t for t in texts if "Start" in t or "End" in t or "Due" in t)
                iurl = link.get_attribute("href") or ""
                items_list.append(ContentItem(
                    name=iname, item_type=item_type, url=iurl, dates=dates,
                ))

            # Attach items to the last module if we can't determine which module they belong to
            if modules and items_list:
                modules[-1].items = [i.name for i in items_list]

            return modules
        except Exception as e:
            print(f"Error getting content: {e}")
            return []

    def get_calendar(self, course_url: str) -> List[Dict]:
        """Scrape today's calendar events for a course."""
        cid = self._course_id(course_url)
        url = f"https://purdue.brightspace.com/d2l/le/calendar/{cid}"
        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)

            events = []
            event_els = self.page.query_selector_all("a.d2l-le-calendar-event")
            for el in event_els:
                time_el = el.query_selector(".d2l-le-calendar-event-time")
                title_el = el.query_selector(".d2l-le-calendar-event-title")
                evt_time = (time_el.text_content() or "").strip() if time_el else ""
                evt_title = (title_el.text_content() or "").strip() if title_el else ""
                if evt_title:
                    events.append({"time": evt_time, "title": evt_title})

            return events
        except Exception as e:
            print(f"Error getting calendar: {e}")
            return []
    
    def _extract_course_code(self, course_name: str) -> str:
        """Extract course code from course name"""
        # Simple regex to extract course codes like "CS 18000" or "MATH 16500"
        import re
        match = re.search(r'([A-Z]{2,4})\s+(\d{5})', course_name)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        return course_name.split(' - ')[0] if ' - ' in course_name else course_name
    
    def _extract_course_from_url(self, url: str) -> str:
        """Extract course name from URL"""
        # Extract course identifier from URL
        parts = url.split('/')
        for part in parts:
            if 'course' in part.lower():
                return part
        return "Unknown Course"
    
    def save_data(self, data: Dict, filename: str):
        """Save scraped data to JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Data saved to {filename}")
        except Exception as e:
            print(f"Error saving data: {e}")


def _has_display() -> bool:
    """Check if a display server is available (X11 or Wayland)."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def scrape(scraper: BrightspaceScraper):
    """Run the actual scraping after authentication."""
    print("Scraping data...")

    courses = scraper.get_courses()
    print(f"Found {len(courses)} courses:")
    for course in courses:
        print(f"  - {course.name} ({course.code})")

    if courses:
        first_course_url = courses[0].url
        if first_course_url:
            assignments = scraper.get_assignments(first_course_url)
            print(f"\nFound {len(assignments)} assignments in {courses[0].name}:")
            for assignment in assignments:
                print(f"  - {assignment.title} (Due: {assignment.due_date})")

    data = {
        "courses": [
            {"name": c.name, "code": c.code, "url": c.url}
            for c in courses
        ],
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    scraper.save_data(data, "brightspace_data.json")


def main():
    """Brightspace scraper with cookie caching for headless environments.

    Flow:
      1. Try cached cookies (headless) — works in LXC / SSH / cron.
      2. If cookies are missing or expired, fall back to a visible browser
         login (requires DISPLAY, e.g. via X11 forwarding: ssh -X).
    """
    USERNAME = os.getenv("PURDUE_USERNAME")
    PASSWORD = os.getenv("PURDUE_PASSWORD")

    if not USERNAME or not PASSWORD:
        print("Error: PURDUE_USERNAME and PURDUE_PASSWORD must be set in .env file")
        return

    # ── 1. Try headless with cached cookies ─────────────────────────
    print("Attempting headless login with cached cookies...")
    with BrightspaceScraper(headless=True) as scraper:
        if scraper.login_with_cookies():
            scrape(scraper)
            return

    # ── 2. Fall back to visible browser for fresh login + Duo ───────
    if not _has_display():
        print(
            "No cached session and no display available.\n"
            "To authenticate, do ONE of the following:\n"
            "  a) SSH with X11 forwarding:  ssh -X user@host\n"
            "  b) Export a DISPLAY:          export DISPLAY=:0\n"
            "Then re-run this script so the browser can open for Duo approval."
        )
        return

    print("Opening browser for Duo Mobile authentication...")
    with BrightspaceScraper(headless=False) as scraper:
        if scraper.login(USERNAME, PASSWORD):
            scrape(scraper)
        else:
            print("Login failed!")


if __name__ == "__main__":
    main()
