import datetime
import logging
import re
import platform
import xml.etree.ElementTree as ET
from enum import Enum, auto
from random import choice, randint, uniform
from time import sleep
from typing import Optional, Tuple

import emoji
from colorama import Fore, Style

from InstaAddict.core.device_facade import (
    DeviceFacade,
    Direction,
    Location,
    Mode,
    SleepTime,
    Timeout,
)
from InstaAddict.core.resources import ClassName
from InstaAddict.core.resources import ResourceID as resources
from InstaAddict.core.resources import TabBarText
from InstaAddict.core.utils import (
    ActionBlockedError,
    Square,
    get_value,
    random_sleep,
    save_crash,
)

logger = logging.getLogger(__name__)


def load_config(config):
    global args
    global configs
    global ResourceID
    args = config.args
    configs = config
    ResourceID = resources(config.args.app_id)


def case_insensitive_re(str_list):
    strings = str_list if isinstance(str_list, str) else "|".join(str_list)
    return f"(?i)({strings})"


class TabBarTabs(Enum):
    HOME = auto()
    SEARCH = auto()
    REELS = auto()
    ORDERS = auto()
    ACTIVITY = auto()
    PROFILE = auto()


class SearchTabs(Enum):
    TOP = auto()
    ACCOUNTS = auto()
    TAGS = auto()
    PLACES = auto()


class FollowStatus(Enum):
    FOLLOW = auto()
    FOLLOWING = auto()
    FOLLOW_BACK = auto()
    REQUESTED = auto()
    NONE = auto()


class SwipeTo(Enum):
    HALF_PHOTO = auto()
    NEXT_POST = auto()


class LikeMode(Enum):
    SINGLE_CLICK = auto()
    DOUBLE_CLICK = auto()


class MediaType(Enum):
    PHOTO = auto()
    VIDEO = auto()
    REEL = auto()
    IGTV = auto()
    CAROUSEL = auto()
    UNKNOWN = auto()


class Owner(Enum):
    OPEN = auto()
    GET_NAME = auto()
    GET_POSITION = auto()


class TabBarView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getTabBar(self):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.TAB_BAR),
            className=ClassName.LINEAR_LAYOUT,
        )

    def is_tab_bar_visible(self) -> bool:
        """The tab bar is only present on the main screens (home, search, profile, ...)."""
        return self._getTabBar().exists(Timeout.SHORT)

    def navigateToHome(self):
        self._navigateTo(TabBarTabs.HOME)
        return HomeView(self.device)

    def navigateToSearch(self):
        self._navigateTo(TabBarTabs.SEARCH)
        return SearchView(self.device)

    def navigateToReels(self):
        self._navigateTo(TabBarTabs.REELS)

    def navigateToOrders(self):
        self._navigateTo(TabBarTabs.ORDERS)

    def navigateToActivity(self):
        self._navigateTo(TabBarTabs.ACTIVITY)

    def navigateToProfile(self):
        self._navigateTo(TabBarTabs.PROFILE)
        return ProfileView(self.device, is_own_profile=True)

    def _get_new_profile_position(self) -> Optional[DeviceFacade.View]:
        buttons = self.device.find(className=ResourceID.BUTTON)
        for button in buttons:
            if button.get_desc() == "Profile":
                return button
        return None

    def _navigateTo(self, tab: TabBarTabs):
        tab_name = tab.name
        logger.debug(f"Navigate to {tab_name}")
        button = None
        UniversalActions.close_keyboard(self.device)
        if tab == TabBarTabs.HOME:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.HOME_CONTENT_DESC),
            )

        elif tab == TabBarTabs.SEARCH:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC),
            )

            if not button.exists():
                # Some accounts display the search btn only in Home -> action bar
                logger.debug("Didn't find search in the tab bar...")
                home_view = self.navigateToHome()
                home_view.navigateToSearch()
                return
        elif tab == TabBarTabs.REELS:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.REELS_CONTENT_DESC),
            )

        elif tab == TabBarTabs.ORDERS:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.ORDERS_CONTENT_DESC),
            )

        elif tab == TabBarTabs.ACTIVITY:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(
                    TabBarText.ACTIVITY_CONTENT_DESC
                ),
            )

        elif tab == TabBarTabs.PROFILE:
            button = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_FRAME_LAYOUT_REGEX,
                descriptionMatches=case_insensitive_re(TabBarText.PROFILE_CONTENT_DESC),
            )
            if not button.exists():
                button = self._get_new_profile_position()

        if button is not None and button.exists(Timeout.MEDIUM):
            # Two clicks to reset tab content
            button.click(sleep=SleepTime.SHORT)
            if tab is not TabBarTabs.PROFILE:
                button.click(sleep=SleepTime.SHORT)
            return

        logger.error(f"Didn't find tab {tab_name} in the tab bar...")


class ActionBarView:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.action_bar = self._getActionBar()

    def _getActionBar(self):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ACTION_BAR_CONTAINER),
            className=ClassName.FRAME_LAYOUT,
        )


class HomeView(ActionBarView):
    def __init__(self, device: DeviceFacade):
        super().__init__(device)
        self.device = device

    def navigateToSearch(self):
        logger.debug("Navigate to Search")
        search_btn = self.action_bar.child(
            descriptionMatches=case_insensitive_re(TabBarText.SEARCH_CONTENT_DESC)
        )
        search_btn.click()

        return SearchView(self.device)


class HashTagView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getRecyclerView(self):
        obj = self.device.find(resourceIdMatches=ResourceID.RECYCLER_VIEW)
        if obj.exists(Timeout.LONG):
            logger.debug("RecyclerView exists.")
        else:
            logger.debug("RecyclerView doesn't exists.")
        return obj

    def _getFistImageView(self, recycler):
        obj = recycler.child(
            resourceIdMatches=ResourceID.IMAGE_BUTTON,
        )
        if obj.exists(Timeout.LONG):
            logger.debug("First image in view exists.")
        else:
            logger.debug("First image in view doesn't exists.")
        return obj

    def _getRecentTab(self):
        obj = self.device.find(
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC),
        )
        if obj.exists(Timeout.LONG):
            logger.debug("Recent Tab exists.")
        else:
            logger.debug("Recent Tab doesn't exists.")
        return obj


# The place view for the moment It's only a copy/paste of HashTagView
# Maybe we can add the com.instagram.android:id/category_name == "Country/Region" (or other obv)


class PlacesView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getRecyclerView(self):
        obj = self.device.find(resourceIdMatches=ResourceID.RECYCLER_VIEW)
        if obj.exists(Timeout.LONG):
            logger.debug("RecyclerView exists.")
        else:
            logger.debug("RecyclerView doesn't exists.")
        return obj

    def _getFistImageView(self, recycler):
        obj = recycler.child(
            resourceIdMatches=ResourceID.IMAGE_BUTTON,
        )
        if obj.exists(Timeout.LONG):
            logger.debug("First image in view exists.")
        else:
            logger.debug("First image in view doesn't exists.")
        return obj

    def _getRecentTab(self):
        return self.device.find(
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(TabBarText.RECENT_CONTENT_DESC),
        )

    def _getInformBody(self):
        return self.device.find(
            className=ClassName.TEXT_VIEW,
            resourceId=ResourceID.INFORM_BODY,
        )


class SearchView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _getSearchEditText(self):
        for _ in range(2):
            obj = self.device.find(
                resourceIdMatches=case_insensitive_re(
                    ResourceID.ACTION_BAR_SEARCH_EDIT_TEXT
                ),
            )
            if obj.exists(Timeout.LONG):
                return obj
            logger.error(
                "Can't find the search bar! Refreshing it by pressing Home and Search again.."
            )
            UniversalActions.close_keyboard(self.device)
            TabBarView(self.device).navigateToHome()
            TabBarView(self.device).navigateToSearch()
        logger.error("Can't find the search bar!")
        return None

    def _getUsernameRow(self, username):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ROW_SEARCH_USER_USERNAME),
            className=ClassName.TEXT_VIEW,
            textMatches=case_insensitive_re(username),
        )

    def _getHashtagRow(self, hashtag):
        return self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.ROW_HASHTAG_TEXTVIEW_TAG_NAME
            ),
            className=ClassName.TEXT_VIEW,
            text=f"#{hashtag}",
        )

    def _getPlaceRow(self):
        obj = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.ROW_PLACE_TITLE),
        )
        obj.wait(Timeout.MEDIUM)
        return obj

    def _getTabTextView(self, tab: SearchTabs):
        tab_layout = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.FIXED_TABBAR_TABS_CONTAINER
            ),
        )
        if tab_layout.exists():
            logger.debug("Tabs container exists!")
            tab_text_view = tab_layout.child(
                resourceIdMatches=case_insensitive_re(ResourceID.TAB_BUTTON_NAME_TEXT),
                textMatches=case_insensitive_re(tab.name),
            )
            if not tab_text_view.exists():
                logger.debug("Tabs container hasn't text! Let's try with description.")
                for obj in tab_layout.child():
                    if obj.ui_info()["contentDescription"].upper() == tab.name.upper():
                        tab_text_view = obj
                        break
            return tab_text_view
        return None

    def _searchTabWithTextPlaceholder(self, tab: SearchTabs):
        tab_layout = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.FIXED_TABBAR_TABS_CONTAINER
            ),
        )
        search_edit_text = self._getSearchEditText()

        fixed_text = "Search {}".format(tab.name if tab.name != "TAGS" else "hashtags")
        logger.debug(
            "Going to check if the search bar have as placeholder: {}".format(
                fixed_text
            )
        )

        for item in tab_layout.child(
            resourceId=ResourceID.TAB_BUTTON_FALLBACK_ICON,
            className=ClassName.IMAGE_VIEW,
        ):
            item.click()

            # Little trick for force-update the ui and placeholder text
            if search_edit_text is not None:
                search_edit_text.click()

            if self.device.find(
                className=ClassName.TEXT_VIEW,
                textMatches=case_insensitive_re(fixed_text),
            ).exists():
                return item
        return None

    def navigate_to_target(self, target: str, job: str) -> bool:
        target = emoji.emojize(target, use_aliases=True)
        logger.info(f"Navigate to {target}")
        search_edit_text = self._getSearchEditText()
        if search_edit_text is not None:
            logger.debug("Pressing on searchbar.")
            search_edit_text.click(sleep=SleepTime.SHORT)
        else:
            logger.debug("There is no searchbar!")
            return False
        if self._check_current_view(target, job):
            logger.info(f"{target} is in recent history.")
            return True
        search_edit_text.set_text(
            target,
            Mode.PASTE if args.dont_type else Mode.TYPE,
        )
        if self._check_current_view(target, job):
            logger.info(f"{target} is in top view.")
            return True
        echo_text = self.device.find(resourceId=ResourceID.ECHO_TEXT)
        if echo_text.exists(Timeout.SHORT):
            logger.debug("Pressing on see all results.")
            echo_text.click()
        # at this point we have the tabs available
        self._switch_to_target_tag(job)
        if self._check_current_view(target, job, in_place_tab=True):
            return True
        return False

    def _switch_to_target_tag(self, job: str):
        if "place" in job:
            tab = SearchTabs.PLACES
        elif "hashtag" in job:
            tab = SearchTabs.TAGS
        else:
            tab = SearchTabs.ACCOUNTS

        obj = self._getTabTextView(tab)
        if obj is not None:
            logger.info(f"Switching to {tab.name}")
            obj.click()

    def _check_current_view(
        self, target: str, job: str, in_place_tab: bool = False
    ) -> bool:
        if "place" in job:
            if not in_place_tab:
                return False
            else:
                obj = self._getPlaceRow()
        else:
            obj = self.device.find(
                text=target,
                resourceIdMatches=ResourceID.SEARCH_ROW_ITEM,
            )
        if obj.exists():
            obj.click()
            return True
        return False


class PostsViewList:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.has_tags = False

    def swipe_to_fit_posts(self, swipe: SwipeTo):
        """calculate the right swipe amount necessary to swipe to next post in hashtag post view
        in order to make it available to other plug-ins I cut it in two moves"""
        displayWidth = self.device.get_info()["displayWidth"]
        displayHeight = self.device.get_info()["displayHeight"]
        containers_content = ResourceID.MEDIA_CONTAINER
        containers_gap = ResourceID.GAP_VIEW_AND_FOOTER_SPACE
        suggested_users = ResourceID.NETEGO_CAROUSEL_HEADER

        # move type: half photo
        if swipe == SwipeTo.HALF_PHOTO:
            media_bounds = self._get_current_media_bounds(containers_content)
            if media_bounds is None:
                logger.debug("Can't find media bounds, using screen fallback.")
                media_bounds = {
                    "top": displayHeight * 0.25,
                    "bottom": displayHeight * 0.75,
                }
            zoomable_view_container = media_bounds["bottom"]
            ac_exists, _, ac_bottom = PostsViewList(
                self.device
            )._get_action_bar_position()
            if ac_exists and zoomable_view_container < ac_bottom:
                zoomable_view_container += ac_bottom
            self.device.swipe_points(
                displayWidth / 2,
                zoomable_view_container - 5,
                displayWidth / 2,
                zoomable_view_container * 0.5,
            )
        elif swipe == SwipeTo.NEXT_POST:
            logger.info(
                "Scroll down to see next post.", extra={"color": f"{Fore.GREEN}"}
            )
            gap_view_obj = self.device.find(index=-1, resourceIdMatches=containers_gap)
            obj1 = None
            for _ in range(3):
                if not gap_view_obj.exists():
                    logger.debug("Can't find the gap obj, scroll down a little more.")
                    PostsViewList(self.device).swipe_to_fit_posts(SwipeTo.HALF_PHOTO)
                    gap_view_obj = self.device.find(resourceIdMatches=containers_gap)
                    if not gap_view_obj.exists():
                        continue
                    else:
                        break
                else:
                    media_bounds = self._get_current_media_bounds(containers_content)
                    if media_bounds and gap_view_obj.get_bounds()["bottom"] < media_bounds["bottom"]:
                        PostsViewList(self.device).swipe_to_fit_posts(
                            SwipeTo.HALF_PHOTO
                        )
                        continue
                    suggested = self.device.find(resourceIdMatches=suggested_users)
                    if suggested.exists():
                        for _ in range(2):
                            PostsViewList(self.device).swipe_to_fit_posts(
                                SwipeTo.HALF_PHOTO
                            )
                            footer_obj = self.device.find(
                                resourceIdMatches=ResourceID.FOOTER_SPACE
                            )
                            if footer_obj.exists():
                                obj1 = footer_obj.get_bounds()["bottom"]
                                break
                    break
            if obj1 is None:
                if gap_view_obj.exists():
                    obj1 = gap_view_obj.get_bounds()["bottom"]
                else:
                    logger.debug(
                        "Gap/footer view not found after retries — likely a "
                        "sponsored/ad post layout. Falling back to content "
                        "container bounds."
                    )
                    fallback_media_bounds = self._get_current_media_bounds(
                        containers_content
                    )
                    obj1 = (
                        fallback_media_bounds["bottom"]
                        if fallback_media_bounds
                        else displayHeight * 0.75
                    )
            media_bounds = self._get_current_media_bounds(containers_content)
            if media_bounds is None:
                logger.debug("Can't find media bounds, using screen fallback.")
                media_bounds = {
                    "top": displayHeight * 0.25,
                    "bottom": displayHeight * 0.75,
                }

            obj2 = (media_bounds["bottom"] + media_bounds["top"]) * 1 / 3

            self.device.swipe_points(
                displayWidth / 2,
                obj1 - 5,
                displayWidth / 2,
                obj2 + 5,
            )
            return True

    def _get_current_media_bounds(self, legacy_media_selector) -> Optional[dict]:
        try:
            media = self.device.find(resourceIdMatches=legacy_media_selector)
            if media.exists() or media.count_items() >= 1:
                return media.get_bounds()
        except Exception as e:
            logger.debug(f"Legacy media bounds lookup failed: {e}")

        try:
            root = ET.fromstring(self.device.deviceV2.dump_hierarchy())
        except Exception as e:
            logger.debug(f"Can't parse UI hierarchy while looking for media: {e}")
            return None

        media_ids = set(ResourceID.MEDIA_CONTAINER.split("|"))
        media_ids.update(ResourceID.CAROUSEL_AND_MEDIA_GROUP.split("|"))
        media_ids.update(
            {
                ResourceID.MEDIA_GROUP,
                ResourceID.VIDEO_CONTAINER,
                f"{configs.args.app_id}:id/row_feed_photo_imageview",
                ResourceID.REEL_VIEWER_MEDIA_CONTAINER,
            }
        )
        display_height = self.device.get_info()["displayHeight"]
        display_width = self.device.get_info()["displayWidth"]

        nodes = []
        for node in root.iter("node"):
            if node.attrib.get("package") != configs.args.app_id:
                continue
            if node.attrib.get("visible-to-user") != "true":
                continue
            bounds = PostsViewList._bounds_from_xml_node(node)
            if bounds is None:
                continue
            nodes.append(
                {
                    "bounds": bounds,
                    "resource_id": node.attrib.get("resource-id", ""),
                    "desc": PostsViewList._normalize_ig_text(
                        node.attrib.get("content-desc")
                    ),
                }
            )

        button_rows = sorted(
            (
                item
                for item in nodes
                if item["resource_id"] == ResourceID.ROW_FEED_VIEW_GROUP_BUTTONS
            ),
            key=lambda item: item["bounds"]["top"],
        )
        media_candidates = []
        for item in nodes:
            bounds = item["bounds"]
            width = bounds["right"] - bounds["left"]
            height = bounds["bottom"] - bounds["top"]
            if width < display_width * 0.5 or height < display_height * 0.08:
                continue
            desc = item["desc"].casefold()
            looks_like_media = (
                item["resource_id"] in media_ids
                or " likes" in desc
                or " comments" in desc
                or desc.startswith(("photo ", "reel by", "video by"))
            )
            if looks_like_media:
                media_candidates.append(item)

        if not media_candidates:
            return None

        for button_row in button_rows:
            row_top = button_row["bounds"]["top"]
            candidates_above_buttons = [
                item
                for item in media_candidates
                if item["bounds"]["top"] < row_top
                and item["bounds"]["bottom"] <= row_top + 4
            ]
            if candidates_above_buttons:
                return max(
                    candidates_above_buttons,
                    key=lambda item: (
                        item["bounds"]["bottom"] - item["bounds"]["top"],
                        item["bounds"]["right"] - item["bounds"]["left"],
                    ),
                )["bounds"]

        visible_candidates = [
            item
            for item in media_candidates
            if 0 <= (item["bounds"]["top"] + item["bounds"]["bottom"]) / 2 <= display_height
        ]
        if not visible_candidates:
            visible_candidates = media_candidates
        return max(
            visible_candidates,
            key=lambda item: (
                item["bounds"]["bottom"] - item["bounds"]["top"],
                -(item["bounds"]["top"]),
            ),
        )["bounds"]

    def _find_likers_container(self):
        universal_actions = UniversalActions(self.device)
        containers_gap = ResourceID.GAP_VIEW_AND_FOOTER_SPACE
        media_container = ResourceID.MEDIA_CONTAINER
        likes = 0
        for _ in range(4):
            gap_view_obj = self.device.find(resourceIdMatches=containers_gap)
            likes_view = self.device.find(
                index=-1,
                resourceId=ResourceID.ROW_FEED_TEXTVIEW_LIKES,
                className=ClassName.TEXT_VIEW,
            )
            description_view = self.device.find(
                resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT
            )
            media = self.device.find(
                resourceIdMatches=media_container,
            )
            try:
                media_count = media.count_items()
            except Exception:
                media_count = 0
            logger.debug(f"I can see {media_count} media(s) in this view..")
            try:
                media_bounds = media.get_bounds() if media_count > 0 else None
            except Exception as e:
                logger.debug(f"Legacy media bounds lookup failed: {e}")
                media_bounds = None
            if media_bounds is None:
                media_bounds = self._get_current_media_bounds(media_container)
                if media_bounds is not None:
                    logger.debug("Using compatibility media bounds.")

            if media_count > 1 and media_bounds and (
                media_bounds["bottom"] < self.device.get_info()["displayHeight"] / 3
            ):
                universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                continue
            if not likes_view.exists():
                likes_fallback = self._get_current_likers_info()
                if likes_fallback is not None:
                    logger.debug("Likers container found in compatibility hierarchy.")
                    return True, self._get_number_of_likers_from_text(
                        likes_fallback["text"]
                    )
                if description_view.exists() or gap_view_obj.exists():
                    return False, likes
                else:
                    universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                    continue
            elif media_bounds and media_bounds["bottom"] > likes_view.get_bounds()["bottom"]:
                universal_actions._swipe_points(Direction.DOWN, delta_y=100)
                continue
            logger.debug("Likers container exists!")
            likes = self._get_number_of_likers(likes_view)
            return likes_view.exists(), likes
        return False, 0

    def _get_current_likers_info(self) -> Optional[dict]:
        try:
            root = ET.fromstring(self.device.deviceV2.dump_hierarchy())
        except Exception as e:
            logger.debug(f"Can't parse UI hierarchy while looking for likers: {e}")
            return None

        nodes = []
        for node in root.iter("node"):
            if node.attrib.get("package") != configs.args.app_id:
                continue
            if node.attrib.get("visible-to-user") != "true":
                continue
            bounds = PostsViewList._bounds_from_xml_node(node)
            if bounds is None:
                continue
            nodes.append(
                {
                    "bounds": bounds,
                    "resource_id": node.attrib.get("resource-id", ""),
                    "text": PostsViewList._normalize_ig_text(node.attrib.get("text")),
                }
            )

        button_rows = sorted(
            (
                item
                for item in nodes
                if item["resource_id"] == ResourceID.ROW_FEED_VIEW_GROUP_BUTTONS
            ),
            key=lambda item: item["bounds"]["top"],
        )
        if not button_rows:
            return None

        likers = []
        for item in nodes:
            text = item["text"]
            if not text:
                continue
            text_lower = text.casefold()
            if (
                text_lower.startswith("liked by ")
                or re.search(r"\b\d[\d,.kmb]*\s+likes?\b", text_lower)
                or text_lower.endswith(" others")
            ):
                likers.append(item)

        for button_row in button_rows:
            row_bottom = button_row["bounds"]["bottom"]
            candidates = [
                item
                for item in likers
                if row_bottom <= item["bounds"]["top"] <= row_bottom + 120
            ]
            if candidates:
                return min(candidates, key=lambda item: item["bounds"]["top"])
        return None

    def _get_number_of_likers_from_text(self, likes_view_text):
        likes = 0
        likes_view_text = PostsViewList._normalize_ig_text(likes_view_text).replace(
            ",", ""
        )
        matches_likes = re.search(
            r"(?P<likes>\d+) (?:others|likes)", likes_view_text, re.IGNORECASE
        )
        matches_view = re.search(
            r"(?P<views>\d+) views", likes_view_text, re.IGNORECASE
        )
        if hasattr(matches_likes, "group"):
            likes = int(matches_likes.group("likes"))
            logger.info(
                f"This post has {likes if 'likes' in likes_view_text else likes + 1} like(s)."
            )
            return likes
        if hasattr(matches_view, "group"):
            views = int(matches_view.group("views"))
            logger.info(
                f"I can see only that this post has {views} views(s). It may contain likes.."
            )
            return -1
        if likes_view_text.endswith("others"):
            logger.info("This post has more than 1 like.")
            return -1
        logger.info("This post has only 1 like.")
        return 1

    def _get_number_of_likers(self, likes_view):
        likes = 0
        if likes_view.exists():
            return self._get_number_of_likers_from_text(likes_view.get_text())
        else:
            logger.info("This post has no likes, skip.")
            return likes

    def open_likers_container(self):
        """Open likes container"""
        post_liked_by_a_following = False
        logger.info("Opening post likers.")
        facepil_stub = self.device.find(
            index=-1, resourceId=ResourceID.ROW_FEED_LIKE_COUNT_FACEPILE_STUB
        )

        if facepil_stub.exists():
            logger.debug("Facepile present, pressing on it!")
            facepil_stub.click()
        else:
            random_sleep(1, 2, modulable=False)
            likes_view = self.device.find(
                index=-1,
                resourceId=ResourceID.ROW_FEED_TEXTVIEW_LIKES,
                className=ClassName.TEXT_VIEW,
            )
            if not likes_view.exists():
                likes_fallback = self._get_current_likers_info()
                if likes_fallback is not None:
                    bounds = likes_fallback["bounds"]
                    logger.debug(f"[DEBUG likers click - compat path] bounds={bounds}")
                    right_edge_point = (
                        bounds["right"] - 15,
                        int((bounds["top"] + bounds["bottom"]) / 2),
                    )
                    self.device.deviceV2.click(*right_edge_point)
                    DeviceFacade.sleep_mode(SleepTime.DEFAULT)
                    return
            if " Liked by" in likes_view.get_text():
                post_liked_by_a_following = True
            elif likes_view.child().count_items() < 2:
                likes_view.click()
                return
            if likes_view.child().exists():
                foil = likes_view.get_bounds()
                # The avatar ("child") sits near the start of the text, and the
                # username right after it is its own clickable span whose exact
                # bounds we can't see via accessibility. Avoiding just the avatar
                # isn't enough -- clicking near the right edge lands past both the
                # avatar and the username link, on "...and X others" instead.
                hole = likes_view.child().get_bounds()
                text = likes_view.get_text()
                logger.debug(
                    f"[DEBUG likers click] text='{text}' | foil={foil} | hole={hole}"
                )
                right_edge_point = (
                    foil["right"] - 15,
                    int((foil["top"] + foil["bottom"]) / 2),
                )
                likes_view.click(Location.CUSTOM, coord=right_edge_point)
                return
            elif not post_liked_by_a_following:
                likes_view.click(Location.RIGHT)
            else:
                likes_view.click(Location.LEFT)

    def _has_tags(self) -> bool:
        tags_icon = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.INDICATOR_ICON_VIEW)
        )
        self.has_tags = tags_icon.exists()
        return self.has_tags

    @staticmethod
    def _bounds_from_xml_node(node):
        bounds = node.attrib.get("bounds", "")
        matches = re.findall(r"\d+", bounds)
        if len(matches) != 4:
            return None
        left, top, right, bottom = map(int, matches)
        return {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        }

    @staticmethod
    def _normalize_ig_text(text):
        return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()

    @staticmethod
    def _node_has_owner_child(node, username):
        username = PostsViewList._normalize_ig_text(username)
        for child in node.iter("node"):
            if child is node:
                continue
            if PostsViewList._normalize_ig_text(child.attrib.get("content-desc")) == username:
                return True
        return False

    @staticmethod
    def _is_caption_text_node(node, username):
        username = PostsViewList._normalize_ig_text(username)
        text = PostsViewList._normalize_ig_text(node.attrib.get("text"))
        if not text.startswith(f"{username} "):
            return False
        resource_id = node.attrib.get("resource-id", "")
        if resource_id in (
            ResourceID.ROW_FEED_PHOTO_PROFILE_NAME,
            ResourceID.ROW_FEED_PROFILE_HEADER,
        ):
            return False
        if node.attrib.get("class", "") == ClassName.BUTTON:
            return False
        return PostsViewList._node_has_owner_child(node, username)

    def _find_caption_text_in_current_post(self, username) -> Optional[str]:
        username = PostsViewList._normalize_ig_text(username)
        media_ids = set(ResourceID.MEDIA_CONTAINER.split("|"))
        try:
            root = ET.fromstring(self.device.deviceV2.dump_hierarchy())
        except Exception as e:
            logger.debug(f"Can't parse UI hierarchy while looking for caption: {e}")
            return None

        nodes = []
        for node in root.iter("node"):
            bounds = PostsViewList._bounds_from_xml_node(node)
            if bounds is None or node.attrib.get("visible-to-user") != "true":
                continue
            nodes.append(
                {
                    "node": node,
                    "bounds": bounds,
                    "resource_id": node.attrib.get("resource-id", ""),
                    "text": PostsViewList._normalize_ig_text(node.attrib.get("text")),
                    "desc": PostsViewList._normalize_ig_text(
                        node.attrib.get("content-desc")
                    ),
                }
            )

        headers = sorted(
            (
                item
                for item in nodes
                if item["resource_id"] == ResourceID.ROW_FEED_PROFILE_HEADER
            ),
            key=lambda item: item["bounds"]["top"],
        )
        button_rows = sorted(
            (
                item
                for item in nodes
                if item["resource_id"] == ResourceID.ROW_FEED_VIEW_GROUP_BUTTONS
            ),
            key=lambda item: item["bounds"]["top"],
        )
        captions = sorted(
            (
                item
                for item in nodes
                if PostsViewList._is_caption_text_node(item["node"], username)
            ),
            key=lambda item: item["bounds"]["top"],
        )

        for button_row in reversed(button_rows):
            next_header_top = min(
                (
                    header["bounds"]["top"]
                    for header in headers
                    if header["bounds"]["top"] > button_row["bounds"]["bottom"]
                ),
                default=self.device.get_info()["displayHeight"] + 1,
            )
            for caption in captions:
                caption_top = caption["bounds"]["top"]
                if button_row["bounds"]["bottom"] <= caption_top < next_header_top:
                    logger.debug("Description found in resource-id-less caption node.")
                    return caption["text"]

        current_headers = [
            header
            for header in headers
            if username in header["desc"] or username in header["text"]
        ]
        for header in reversed(current_headers):
            next_header_top = min(
                (
                    other["bounds"]["top"]
                    for other in headers
                    if other["bounds"]["top"] > header["bounds"]["top"]
                ),
                default=self.device.get_info()["displayHeight"] + 1,
            )
            has_media = any(
                item["resource_id"] in media_ids
                and header["bounds"]["top"] <= item["bounds"]["top"] < next_header_top
                for item in nodes
            )
            if not has_media:
                continue
            for caption in captions:
                if header["bounds"]["top"] <= caption["bounds"]["top"] < next_header_top:
                    logger.debug("Description found in current post hierarchy.")
                    return caption["text"]
        return None

    def _check_if_last_post(
        self, last_description, current_job
    ) -> Tuple[bool, str, str, bool, bool, bool]:
        """check if that post has been just interacted"""
        universal_actions = UniversalActions(self.device)
        username, is_ad, is_hashtag = PostsViewList(self.device)._post_owner(
            current_job, Owner.GET_NAME
        )
        username = PostsViewList._normalize_ig_text(username)
        has_tags = self._has_tags()
        for _ in range(8):
            post_description = self.device.find(
                index=-1,
                resourceIdMatches=ResourceID.ROW_FEED_TEXT,
                textStartsWith=username,
            )
            if not post_description.exists() and post_description.count_items() >= 1:
                text = post_description.get_text()
                post_description = self.device.find(
                    index=-1,
                    resourceIdMatches=ResourceID.ROW_FEED_TEXT,
                    text=text,
                )
            if post_description.exists():
                logger.debug("Description found!")
                new_description = post_description.get_text().upper()
                if new_description != last_description:
                    return False, new_description, username, is_ad, is_hashtag, has_tags
                logger.info(
                    "This post has the same description and author as the last one."
                )
                return True, new_description, username, is_ad, is_hashtag, has_tags
            caption_text = self._find_caption_text_in_current_post(username)
            if caption_text:
                new_description = caption_text.upper()
                if new_description != last_description:
                    return False, new_description, username, is_ad, is_hashtag, has_tags
                logger.info(
                    "This post has the same description and author as the last one."
                )
                return True, new_description, username, is_ad, is_hashtag, has_tags
            else:
                gap_view_obj = self.device.find(resourceId=ResourceID.GAP_VIEW)
                feed_composer = self.device.find(
                    resourceId=ResourceID.FEED_INLINE_COMPOSER_BUTTON_TEXTVIEW
                )
                if gap_view_obj.exists() and gap_view_obj.get_bounds()["bottom"] < (
                    self.device.get_info()["displayHeight"] / 3
                ):
                    universal_actions._swipe_points(
                        direction=Direction.DOWN, delta_y=200
                    )
                    continue
                row_feed_profile_header = self.device.find(
                    resourceId=ResourceID.ROW_FEED_PROFILE_HEADER
                )
                if row_feed_profile_header.count_items() > 1:
                    logger.info("This post hasn't the description...")
                    return False, "", username, is_ad, is_hashtag, has_tags
                profile_header_is_above = row_feed_profile_header.is_above_this(
                    gap_view_obj if gap_view_obj.exists() else feed_composer
                )
                if profile_header_is_above is not None:
                    if not profile_header_is_above:
                        logger.info("This post hasn't the description...")
                        return False, "", username, is_ad, is_hashtag, has_tags

                logger.debug(self.device.dump_hierarchy("window.xml"))
                logger.debug(
                    f"Can't find the description of {username}'s post, try to swipe a little bit down."
                )
                universal_actions._swipe_points(direction=Direction.DOWN, delta_y=200)
        logger.info("This post hasn't the description...")
        return False, "", username, is_ad, is_hashtag, has_tags

    def _if_action_bar_is_over_obj_swipe(self, obj):
        """do a swipe of the amount of the action bar"""
        action_bar_exists, _, action_bar_bottom = PostsViewList(
            self.device
        )._get_action_bar_position()
        if action_bar_exists:
            obj_top = obj.get_bounds()["top"]
            if action_bar_bottom > obj_top:
                UniversalActions(self.device)._swipe_points(
                    direction=Direction.UP, delta_y=action_bar_bottom
                )

    def _get_action_bar_position(self) -> Tuple[bool, int, int]:
        """action bar is overlay, if you press on it, you go back to the first post
        knowing his position is important to avoid it: exists, top, bottom"""
        action_bar = self.device.find(resourceIdMatches=ResourceID.ACTION_BAR_CONTAINER)
        if action_bar.exists():
            return (
                True,
                action_bar.get_bounds()["top"],
                action_bar.get_bounds()["bottom"],
            )
        else:
            return False, 0, 0

    def _refresh_feed(self):
        logger.info("Refresh feed..")
        refresh_pill = self.device.find(resourceId=ResourceID.NEW_FEED_PILL)
        if refresh_pill.exists(Timeout.SHORT):
            refresh_pill.click()
            random_sleep(inf=5, sup=8, modulable=False)
        else:
            UniversalActions(self.device)._reload_page()

    def _post_owner(self, current_job, mode: Owner, username=None):
        """returns a tuple[var, bool, bool]"""
        is_ad = False
        is_hashtag = False
        if username is None:
            post_owner_obj = self.device.find(
                resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME
            )
        else:
            for _ in range(2):
                post_owner_obj = self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME,
                    textStartsWith=username,
                )
                notification = self.device.find(
                    resourceIdMatches=ResourceID.NOTIFICATION_MESSAGE
                )
                if not post_owner_obj.exists and notification.exists():
                    logger.warning(
                        "There is a notification there! Please disable them in settings.. We will wait 10 seconds before continue.."
                    )
                    sleep(10)
        post_owner_clickable = False

        for _ in range(3):
            if not post_owner_obj.exists():
                if mode == Owner.OPEN:
                    comment_description = self.device.find(
                        resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT,
                        textStartsWith=username,
                    )
                    if (
                        not comment_description.exists()
                        and comment_description.count_items() >= 1
                    ):
                        comment_description = self.device.find(
                            resourceIdMatches=ResourceID.ROW_FEED_COMMENT_TEXTVIEW_LAYOUT,
                            text=comment_description.get_text(),
                        )

                    if comment_description.exists():
                        logger.info("Open post owner from description.")
                        comment_description.child().click()
                        return True, is_ad, is_hashtag
                UniversalActions(self.device)._swipe_points(direction=Direction.UP)
                post_owner_obj = self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME,
                )
            else:
                post_owner_clickable = True
                break

        if not post_owner_clickable:
            logger.info("Can't find the owner name, skip.")
            return False, is_ad, is_hashtag
        if mode == Owner.OPEN:
            logger.info("Open post owner.")
            PostsViewList(self.device)._if_action_bar_is_over_obj_swipe(post_owner_obj)
            post_owner_obj.click()
            return True, is_ad, is_hashtag
        elif mode == Owner.GET_NAME:
            if current_job == "feed":
                is_ad, is_hashtag, username = PostsViewList(
                    self.device
                )._check_if_ad_or_hashtag(post_owner_obj)
            if username is None:
                raw_text = post_owner_obj.get_text()
                logger.debug(f"[DEBUG owner name] raw_text='{raw_text}'")
                username = (
                    post_owner_obj.get_text().replace("•", "").strip().split(" ", 1)[0]
                )
            return username, is_ad, is_hashtag

        elif mode == Owner.GET_POSITION:
            return post_owner_obj.get_bounds(), is_ad
        else:
            return None, is_ad, is_hashtag

    def _get_post_owner_name(self):
        return self.device.find(
            resourceIdMatches=ResourceID.ROW_FEED_PHOTO_PROFILE_NAME
        ).get_text()

    def _get_media_container(self):
        media = self.device.find(resourceIdMatches=ResourceID.CAROUSEL_AND_MEDIA_GROUP)
        content_desc = media.get_desc() if media.exists() else None
        return media, content_desc

    @staticmethod
    def detect_media_type(content_desc) -> Tuple[Optional[MediaType], Optional[int]]:
        """
        Detect the nature and amount of a media
        :return: MediaType and count
        :rtype: MediaType, int
        """
        obj_count = 1
        if content_desc is None:
            return None, None
        if re.match(r"^,|^\s*$", content_desc, re.IGNORECASE):
            logger.info(
                "That media is missing content description, so I don't know which kind of video it is."
            )
            media_type = MediaType.UNKNOWN
        elif re.match(r"^Photo|^Hidden Photo", content_desc, re.IGNORECASE):
            logger.info("It's a photo.")
            media_type = MediaType.PHOTO
        elif re.match(r"^Video|^Hidden Video", content_desc, re.IGNORECASE):
            logger.info("It's a video.")
            media_type = MediaType.VIDEO
        elif re.match(r"^IGTV", content_desc, re.IGNORECASE):
            logger.info("It's a IGTV.")
            media_type = MediaType.IGTV
        elif re.match(r"^Reel", content_desc, re.IGNORECASE):
            logger.info("It's a Reel.")
            media_type = MediaType.REEL
        else:
            carousel_obj = re.finditer(
                r"((?P<photo>\d+) photo)|((?P<video>\d+) video)",
                content_desc,
                re.IGNORECASE,
            )
            n_photos = 0
            n_videos = 0
            for match in carousel_obj:
                if match.group("photo"):
                    n_photos = int(match.group("photo"))
                if match.group("video"):
                    n_videos = int(match.group("video"))
            logger.info(
                f"It's a carousel with {n_photos} photo(s) and {n_videos} video(s)."
            )
            obj_count = n_photos + n_videos
            media_type = MediaType.CAROUSEL
        return media_type, obj_count

    def _like_in_post_view(
        self,
        mode: LikeMode,
        skip_media_check: bool = False,
        already_watched: bool = False,
    ):
        post_view_list = PostsViewList(self.device)
        opened_post_view = OpenedPostView(self.device)
        if skip_media_check:
            return
        media, content_desc = self._get_media_container()
        if content_desc is None:
            return
        if not already_watched:
            media_type, _ = post_view_list.detect_media_type(content_desc)
            opened_post_view.watch_media(media_type)
        if mode == LikeMode.DOUBLE_CLICK:
            if media_type in (MediaType.CAROUSEL, MediaType.PHOTO):
                logger.info("Double click on post.")
                _, _, action_bar_bottom = PostsViewList(
                    self.device
                )._get_action_bar_position()
                media.double_click(obj_over=action_bar_bottom)
            else:
                self._like_in_post_view(
                    mode=LikeMode.SINGLE_CLICK, skip_media_check=True
                )
        elif mode == LikeMode.SINGLE_CLICK:
            like_button_exists, _ = self._find_likers_container()
            if like_button_exists:
                logger.info("Clicking on the little heart ❤️.")
                self.device.find(
                    resourceIdMatches=ResourceID.ROW_FEED_BUTTON_LIKE
                ).click()

    def _follow_in_post_view(self):
        logger.info("Follow blogger in place.")
        self.device.find(resourceIdMatches=ResourceID.BUTTON).click()

    def _comment_in_post_view(self):
        logger.info("Open comments of post.")
        self.device.find(resourceIdMatches=ResourceID.ROW_FEED_BUTTON_COMMENT).click()

    def _check_if_liked(self):
        logger.debug("Check if like succeeded in post view.")
        bnt_like_obj = self.device.find(
            resourceIdMatches=ResourceID.ROW_FEED_BUTTON_LIKE
        )
        if bnt_like_obj.exists():
            STR = "Liked"
            if self.device.find(descriptionMatches=case_insensitive_re(STR)).exists():
                logger.debug("Like is present.")
                return True
            else:
                logger.debug("Like is not present.")
                return False
        else:
            UniversalActions(self.device)._swipe_points(
                direction=Direction.DOWN, delta_y=100
            )
            return PostsViewList(self.device)._check_if_liked()

    def _check_if_ad_or_hashtag(
        self, post_owner_obj
    ) -> Tuple[bool, bool, Optional[str]]:
        is_hashtag = False
        is_ad = False
        logger.debug("Checking if it's an AD or an hashtag..")
        ad_like_obj = post_owner_obj.sibling(
            resourceId=ResourceID.SECONDARY_LABEL,
        )

        owner_name = post_owner_obj.get_text() or post_owner_obj.get_desc() or ""
        if not owner_name:
            logger.info("Can't find the owner name, need to use OCR.")
            try:
                import pytesseract as pt

                owner_name = self.get_text_from_screen(pt, post_owner_obj)
            except ImportError:
                logger.error(
                    "You need to install pytesseract (the wrapper: pip install pytesseract) in order to use OCR feature."
                )
            except pt.TesseractNotFoundError:
                logger.error(
                    "You need to install Tesseract (the engine: it depends on your system) in order to use OCR feature."
                )
        if owner_name.startswith("#"):
            is_hashtag = True
            logger.debug("Looks like an hashtag, skip.")
        if ad_like_obj.exists():
            ad_labels = {"sponsored", "ad"}
            ad_like_txt = ad_like_obj.get_text() or ad_like_obj.get_desc() or ""
            if ad_like_txt.casefold() in ad_labels:
                logger.debug(f"Looks like an AD (label: '{ad_like_txt}'), skip.")
                is_ad = True
            elif is_hashtag:
                owner_name = owner_name.split("•")[0].strip()

        return is_ad, is_hashtag, owner_name

    def get_text_from_screen(self, pt, obj) -> Optional[str]:

        if platform.system() == "Windows":
            pt.pytesseract.tesseract_cmd = (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )

        screenshot = self.device.screenshot()
        bounds = obj.ui_info().get("visibleBounds", None)
        if bounds is None:
            logger.info("Can't find the bounds of the object.")
            return None
        screenshot_cropped = screenshot.crop(
            [
                bounds.get("left"),
                bounds.get("top"),
                bounds.get("right"),
                bounds.get("bottom"),
            ]
        )
        return pt.image_to_string(screenshot_cropped).split(" ")[0].rstrip()


class LanguageView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def setLanguage(self, language: str):
        logger.debug(f"Set language to {language}.")
        search_edit_text = self.device.find(
            resourceId=ResourceID.SEARCH,
            className=ClassName.EDIT_TEXT,
        )
        search_edit_text.set_text(language, Mode.PASTE if args.dont_type else Mode.TYPE)

        list_view = self.device.find(
            resourceId=ResourceID.LANGUAGE_LIST_LOCALE,
            className=ClassName.LIST_VIEW,
        )
        first_item = list_view.child(index=0)
        first_item.click()
        random_sleep()


class AccountView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def navigateToLanguage(self):
        logger.debug("Navigate to Language")
        button = self.device.find(
            className=ClassName.BUTTON,
            index=6,
        )
        if button.exists():
            button.click()
            return LanguageView(self.device)
        else:
            logger.error("Not able to set your app in English! Do it by yourself!")
            exit(0)

    def navigate_to_main_account(self):
        logger.debug("Navigating to main account...")
        profile_view = ProfileView(self.device)
        profile_view.click_on_avatar()
        if profile_view.getFollowingCount() is None:
            profile_view.click_on_avatar()

    def changeToUsername(self, username: str):
        action_bar = ProfileView._getActionBarTitleBtn(self)
        if action_bar is not None:
            current_profile_name = action_bar.get_text()
            # in private accounts there is little lock which is codec as two spaces (should be \u1F512)
            if current_profile_name.strip().upper() == username.upper():
                logger.info(
                    f"You are already logged as {username}!",
                    extra={"color": f"{Style.BRIGHT}{Fore.BLUE}"},
                )
                return True
            logger.debug(f"You're logged as {current_profile_name.strip()}")
            selector = self.device.find(resourceId=ResourceID.ACTION_BAR_TITLE_CHEVRON)
            selector.click()
            if self._find_username(username):
                if action_bar is not None:
                    current_profile_name = action_bar.get_text()
                    if current_profile_name.strip().upper() == username.upper():
                        return True
                else:
                    logger.error(
                        "Cannot find action bar (where you select your account)!"
                    )
        return False

    def _find_username(self, username, has_scrolled=False):
        list_view = self.device.find(resourceId=ResourceID.LIST)
        username_obj = self.device.find(
            resourceIdMatches=f"{ResourceID.ROW_USER_TEXTVIEW}|{ResourceID.USERNAME_TEXTVIEW}",
            textMatches=case_insensitive_re(username),
        )
        if username_obj.exists(Timeout.SHORT):
            logger.info(
                f"Switching to {username}...",
                extra={"color": f"{Style.BRIGHT}{Fore.BLUE}"},
            )
            username_obj.click()
            return True

        # Fallback for IG 438+: account switcher uses content-desc on ViewGroup rows
        account_row = self.device.find(
            classNameMatches="android.view.ViewGroup",
            descriptionMatches=case_insensitive_re(f"^{username}.*"),
        )
        if account_row.exists(Timeout.SHORT):
            logger.info(
                f"Switching to {username}...",
                extra={"color": f"{Style.BRIGHT}{Fore.BLUE}"},
            )
            account_row.click()
            return True

        if list_view.exists() and list_view.is_scrollable() and not has_scrolled:
            logger.debug("User list is scrollable.")
            list_view.scroll(Direction.DOWN)
            return self._find_username(username, has_scrolled=True)
        return False

    def refresh_account(self):
        textview = self.device.find(
            resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_POST_CONTAINER
        )
        universal_actions = UniversalActions(self.device)
        if textview.exists(Timeout.SHORT):
            logger.info("Refresh account...")
            universal_actions._swipe_points(
                direction=Direction.UP,
                start_point_y=textview.get_bounds()["bottom"],
                delta_y=280,
            )
            random_sleep(modulable=False)
        obj = self.device.find(
            resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_POST_CONTAINER
        )
        if not obj.exists(Timeout.MEDIUM):
            logger.debug(
                "Can't see Posts, Followers and Following after the refresh, maybe we moved a little bit bottom.. Swipe down."
            )
            universal_actions._swipe_points(Direction.UP)


class SettingsView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def navigateToAccount(self):
        logger.debug("Navigate to Account")
        button = self.device.find(
            className=ClassName.BUTTON,
            index=5,
        )
        if button.exists():
            button.click()
            return AccountView(self.device)
        else:
            logger.error("Not able to set your app in English! Do it by yourself!")
            exit(2)


class OptionsView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def navigateToSettings(self):
        logger.debug("Navigate to Settings")
        button = self.device.find(
            resourceId=ResourceID.MENU_OPTION_TEXT,
            className=ClassName.TEXT_VIEW,
        )
        if button.exists():
            button.click()
            return SettingsView(self.device)
        else:
            logger.error("Not able to set your app in English! Do it by yourself!")
            exit(0)


class OpenedPostView:
    def __init__(self, device: DeviceFacade):
        self.device = device
        self.has_tags = False

    def is_post_opened(self) -> bool:
        """Confirm a post detail or the reels viewer is actually showing."""
        post_media = self.device.find(
            resourceIdMatches=case_insensitive_re(
                "|".join(
                    [
                        ResourceID.MEDIA_CONTAINER,
                        ResourceID.VIDEO_CONTAINER_AND_CLIPS_VIDEO_CONTAINER,
                        ResourceID.ROW_FEED_BUTTON_LIKE,
                        ResourceID.LIKE_BUTTON,
                    ]
                )
            )
        )
        return post_media.exists(Timeout.MEDIUM)

    def detect_opened_media_type(self) -> MediaType:
        """Detect the media type from the opened post itself.
        Used when the grid cell had no content description."""
        clips_container = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.CLIPS_VIDEO_CONTAINER)
        )
        if clips_container.exists():
            logger.info("It's a Reel (detected after opening).")
            return MediaType.REEL
        video_container = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.VIDEO_CONTAINER)
        )
        if video_container.exists():
            play_button = self.device.find(
                resourceIdMatches=case_insensitive_re(ResourceID.VIEW_PLAY_BUTTON)
            )
            timer = self.device.find(resourceId=ResourceID.TIMER)
            if play_button.exists() or timer.exists():
                logger.info("It's a video (detected after opening).")
                return MediaType.VIDEO
            logger.debug(
                "video_container is present but there's no play button or timer - not a video."
            )
        carousel_indicator = self.device.find(
            resourceIdMatches=case_insensitive_re(
                f"{ResourceID.CAROUSEL_MEDIA_GROUP}|{ResourceID.CAROUSEL_INDEX_INDICATOR_TEXT_VIEW}"
            )
        )
        if carousel_indicator.exists():
            logger.info("It's a carousel (detected after opening).")
            return MediaType.CAROUSEL
        logger.info("It's a photo (detected after opening).")
        return MediaType.PHOTO

    def _get_post_like_button(self) -> Optional[DeviceFacade.View]:
        post_media_view = self.device.find(resourceIdMatches=ResourceID.MEDIA_CONTAINER)
        if post_media_view.exists(Timeout.MEDIUM):
            attempt = 0
            while True:
                like_button = post_media_view.down(
                    resourceIdMatches=ResourceID.ROW_FEED_BUTTON_LIKE
                )
                if like_button.viewV2 is not None or attempt == 3:
                    return like_button if like_button.exists() else None
                UniversalActions(self.device)._swipe_points(
                    direction=Direction.DOWN, delta_y=100
                )
                attempt += 1
        return None

    def _is_post_liked(self) -> Tuple[Optional[bool], Optional[DeviceFacade.View]]:
        """
        Check if post is liked
        :return: post is liked or not
        :rtype: bool
        """
        like_btn_view = self._get_post_like_button()
        if not like_btn_view:
            return False, None

        return like_btn_view.get_selected(), like_btn_view

    def like_post(self) -> bool:
        """
        Like the post with a double click and check if it's liked
        :return: post has been liked
        :rtype: bool
        """
        post_media_view = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.MEDIA_CONTAINER)
        )
        liked = False
        if not post_media_view.exists():
            like_button = self.device.find(
                resourceIdMatches=case_insensitive_re(ResourceID.ROW_FEED_BUTTON_LIKE)
            )
            if like_button.exists(Timeout.SHORT):
                logger.info("Liking post via the little heart ❤️.")
                like_button.click()
                UniversalActions.detect_block(self.device)
                liked = like_button.get_selected()
            else:
                logger.error("Can't find the media container nor the like button!")
        elif post_media_view.exists():
            logger.info("Liking post.")
            if self.has_tags:
                logger.info(
                    "Post has tags, better going with a single click on the little heart ❤️."
                )
                like_button = self._get_post_like_button()
                if like_button is not None:
                    like_button.click()
                    liked, _ = self._is_post_liked()
                else:
                    logger.warning("Can't find the like button object!")
            else:
                post_media_view.double_click()
                liked, like_button = self._is_post_liked()
                if not liked and like_button is not None:
                    logger.info("Double click failed, clicking on the little heart ❤️.")
                    like_button.click()
                    liked, _ = self._is_post_liked()
        return liked

    def start_video(self) -> bool:
        """
        Press on play button if present
        :return: has play button been pressed
        :rtype: bool
        """
        play_button = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.VIEW_PLAY_BUTTON)
        )
        if play_button.exists(Timeout.TINY):
            logger.debug("Pressing on play button.")
            play_button.click()
            return True
        return False

    def open_video(self) -> bool:
        """
        Open video in full-screen mode
        :return: video in full-screen mode
        :rtype: bool
        """
        in_fullscreen, _ = self._is_video_in_fullscreen()
        if in_fullscreen:
            logger.debug("Video is already in full screen.")
            return True
        post_media_view = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.MEDIA_CONTAINER)
        )
        if post_media_view.exists():
            logger.info("Going in full screen.")
            post_media_view.click()
            in_fullscreen, _ = self._is_video_in_fullscreen()
        return in_fullscreen

    def watch_media(self, media_type: MediaType) -> None:
        """
        Watch media for the amount of time specified in config
        :return: None
        :rtype: None
        """
        if (
            media_type
            in (MediaType.IGTV, MediaType.REEL, MediaType.VIDEO, MediaType.UNKNOWN)
            and args.watch_video_time != "0"
        ):
            in_fullscreen, _ = self._is_video_in_fullscreen()
            time_left = self._get_video_time_left()
            watching_time = get_value(
                args.watch_video_time, name=None, default=0, its_time=True
            )
            if time_left > 0 and media_type != MediaType.REEL and in_fullscreen:
                logger.info(f"This video is about {time_left}s long.")
                # hardcoded 5 seconds, so we have the time to doing everything without going to the next video, hopefully
                watching_time = min(
                    watching_time,
                    time_left - 5,
                )
            logger.info(
                f"Watching video for {watching_time if watching_time > 0 else 'few '}s."
            )

        elif (
            media_type in (MediaType.CAROUSEL, MediaType.PHOTO)
            and args.watch_photo_time != "0"
        ):
            self._has_tags()
            watching_time = get_value(
                args.watch_photo_time, "Watching photo for {}s.", 0, its_time=True
            )
        else:
            return None
        if watching_time > 0:
            sleep(watching_time)

    def _get_video_time_left(self) -> int:
        timer = self.device.find(resourceId=ResourceID.TIMER)
        if timer.exists():
            raw_time = timer.get_text().split(":")
            try:
                return int(raw_time[0]) * 60 + int(raw_time[1])
            except (IndexError, ValueError):
                return 0
        return 0

    def _is_video_in_fullscreen(self) -> Tuple[bool, DeviceFacade.View]:
        """
        Check if video is in full-screen mode
        """
        video_container = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.VIDEO_CONTAINER_AND_CLIPS_VIDEO_CONTAINER
            )
        )
        return video_container.exists(), video_container

    def _is_video_liked(self) -> Tuple[Optional[bool], Optional[DeviceFacade.View]]:
        """
        Check if video has been liked
        """
        like_button = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.LIKE_BUTTON)
        )
        if like_button.exists():
            return like_button.get_selected(), like_button
        return False, None

    def _has_tags(self) -> bool:
        tags_icon = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.INDICATOR_ICON_VIEW)
        )
        self.has_tags = tags_icon.exists()
        return self.has_tags

    def like_video(self) -> bool:
        """
        Like the video with a double click and check if it's liked
        :return: video has been liked
        :rtype: bool
        """
        sidebar = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.UFI_STACK)
        )
        liked = False
        full_screen, obj = self._is_video_in_fullscreen()
        if full_screen:
            logger.info("Liking video.")
            obj.double_click()
            UniversalActions.detect_block(self.device)
            if not sidebar.exists():
                logger.debug("Showing sidebar...")
                obj.click()
            liked, like_button = self._is_video_liked()
            if not liked:
                logger.info("Double click failed, clicking on the little heart ❤️.")
                if like_button is not None:
                    like_button.click()
                    UniversalActions.detect_block(self.device)
                else:
                    logger.error("We are seeing another video.")
                liked, _ = self._is_video_liked()
        return liked

    def _getListViewLikers(self):
        for _ in range(2):
            obj = self.device.find(resourceId=ResourceID.LIST)
            if obj.exists(Timeout.LONG):
                return obj
            logger.debug("Can't find likers list, try again..")
        logger.error("Can't load likers list..")
        return None

    def _getUserContainer(self):
        obj = self.device.find(
            resourceIdMatches=ResourceID.USER_LIST_CONTAINER,
        )
        return obj if obj.exists(Timeout.LONG) else None

    def _getUserName(self, container):
        return container.child(
            resourceId=ResourceID.ROW_USER_PRIMARY_NAME,
        )

    def _isFollowing(self, container):
        text = container.child(
            resourceId=ResourceID.BUTTON,
            classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
        )
        if not isinstance(text, str):
            text = text.get_text() if text.exists() else ""
        return text in ["Following", "Requested"]


class PostsGridView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def scrollDown(self):
        coordinator_layout = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.COORDINATOR_ROOT_LAYOUT)
        )
        if coordinator_layout.exists():
            coordinator_layout.scroll(Direction.DOWN)
            return True

        return False

    def _get_post_view(self):
        return self.device.find(resourceIdMatches=case_insensitive_re(ResourceID.LIST))

    def _is_still_on_profile(self) -> bool:
        """The profile tab bar is only visible while no post is opened."""
        profile_tabs = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_TABS_CONTAINER)
        )
        return profile_tabs.exists(Timeout.SHORT)

    def navigateToPost(self, row, col):
        post_list_view = self._get_post_view()
        post_list_view.wait(Timeout.MEDIUM)
        OFFSET = 1  # row with post starts from index 1
        row_view = post_list_view.child(index=row + OFFSET)
        if not row_view.exists():
            return None, None, None
        post_view = row_view.child(index=col)
        if not post_view.exists():
            return None, None, None
        content_desc = post_view.ui_info()["contentDescription"]
        media_type, obj_count = PostsViewList.detect_media_type(content_desc)
        opened_post_view = OpenedPostView(self.device)
        for attempt in range(2):
            post_view.click()
            if opened_post_view.is_post_opened() or not self._is_still_on_profile():
                return opened_post_view, media_type, obj_count
            if attempt == 0:
                logger.debug("Post didn't open, trying one more click...")
                post_view = row_view.child(index=col)
                if not post_view.exists():
                    break
        logger.debug(
            f"Click on row {row}, column {col} didn't open any post (empty grid slot?)."
        )
        return None, None, None


class ProfileView(ActionBarView):
    def __init__(self, device: DeviceFacade, is_own_profile=False):
        super().__init__(device)
        self.device = device
        self.is_own_profile = is_own_profile

    def navigateToOptions(self):
        logger.debug("Navigate to Options")
        button = self.action_bar.child(index=2)
        button.click()

        return OptionsView(self.device)

    def _getActionBarTitleBtn(self, watching_stories=False):
        bar = case_insensitive_re(
            [
                ResourceID.TITLE_VIEW,
                ResourceID.ACTION_BAR_TITLE,
                ResourceID.ACTION_BAR_LARGE_TITLE,
                ResourceID.ACTION_BAR_TEXTVIEW_TITLE,
                ResourceID.ACTION_BAR_TITLE_AUTO_SIZE,
                ResourceID.ACTION_BAR_LARGE_TITLE_AUTO_SIZE,
            ]
        )
        action_bar = self.device.find(
            resourceIdMatches=bar,
        )
        if not watching_stories and action_bar.exists(Timeout.LONG) or watching_stories:
            return action_bar
        logger.error(
            "Unable to find action bar! (The element with the username at top)"
        )
        return None

    def _getSomeText(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Get some text from the profile to check the language"""
        obj = self.device.find(
            resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_POST_CONTAINER
        )
        if not obj.exists(Timeout.MEDIUM):
            UniversalActions(self.device)._swipe_points(Direction.UP)
        try:
            post = (
                self.device.find(
                    resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_POST_CONTAINER
                )
                .child(index=1)
                .get_text()
            )
            followers = (
                self.device.find(
                    resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_FOLLOWERS_CONTAINER
                )
                .child(index=1)
                .get_text()
            )
            following = (
                self.device.find(
                    resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_FOLLOWING_CONTAINER
                )
                .child(index=1)
                .get_text()
            )
            return post.casefold(), followers.casefold(), following.casefold()
        except Exception as e:
            logger.debug(f"Exception: {e}")
            logger.warning(
                "Can't get post/followers/following text for check the language! Save a crash to understand the reason."
            )
            save_crash(self.device)
            return None, None, None

    def _new_ui_profile_button(self) -> bool:
        found = False
        buttons = self.device.find(className=ResourceID.BUTTON)
        for button in buttons:
            if button.get_desc() == "Profile":
                button.click()
                found = True
        return found

    def _old_ui_profile_button(self) -> bool:
        found = False
        obj = self.device.find(resourceIdMatches=ResourceID.TAB_AVATAR)
        if obj.exists(Timeout.MEDIUM):
            obj.click()
            found = True
        return found

    def click_on_avatar(self):
        while True:
            if self._new_ui_profile_button():
                break
            if self._old_ui_profile_button():
                break
            self.device.back()

    def getFollowButton(self):
        button_regex = f"{ClassName.BUTTON}|{ClassName.TEXT_VIEW}"
        following_regex_all = "^following|^requested|^follow back|^follow"
        following_or_follow_back_button = self.device.find(
            classNameMatches=button_regex,
            clickable=True,
            textMatches=case_insensitive_re(following_regex_all),
        )
        if following_or_follow_back_button.exists(Timeout.MEDIUM):
            button_text = following_or_follow_back_button.get_text().casefold()
            if button_text in ["following", "requested"]:
                button_status = FollowStatus.FOLLOWING
            elif button_text == "follow back":
                button_status = FollowStatus.FOLLOW_BACK
            else:
                button_status = FollowStatus.FOLLOW
            return following_or_follow_back_button, button_status
        else:
            logger.warning(
                "The follow button doesn't exist! Maybe the profile is not loaded!"
            )
            return None, FollowStatus.NONE

    def getUsername(self, watching_stories=False):
        action_bar = self._getActionBarTitleBtn(watching_stories)
        if action_bar is not None:
            return action_bar.get_text(error=not watching_stories).strip()
        if not watching_stories:
            logger.error("Cannot get username.")
        return None

    def getLinkInBio(self):
        obj = self.device.find(resourceIdMatches=ResourceID.PROFILE_HEADER_WEBSITE)
        if obj.exists():
            website = obj.get_text()
            return website if website != "" else None
        return None

    def getMutualFriends(self) -> int:
        logger.debug("Looking for mutual friends tab.")
        follow_context = self.device.find(
            resourceIdMatches=ResourceID.PROFILE_HEADER_FOLLOW_CONTEXT_TEXT
        )
        if follow_context.exists():
            text = follow_context.get_text()
            mutual_friends = re.finditer(
                r"((?P<others>\s\d+\s)|(?P<extra>,))",
                text,
                re.IGNORECASE,
            )
            n_others = 0
            n_extra = 0
            for match in mutual_friends:
                if match.group("others"):
                    n_others = int(match.group("others"))
                if match.group("extra"):
                    n_extra = 2
            if n_others != 0:
                mutual_friends = n_others + n_extra if n_extra != 0 else n_others + 1
            else:
                mutual_friends = n_extra if n_extra != 0 else 1
        else:
            mutual_friends = 0
        return mutual_friends

    def _parseCounter(self, raw_text: str) -> Optional[int]:
        multiplier = 1
        regex = r"(?!(K|M|\.))\D+"
        subst = "."
        text = re.sub(regex, subst, raw_text)
        if "K" in text:
            value = float(text.replace("K", ""))
            multiplier = 1_000
        elif "M" in text:
            value = float(text.replace("M", ""))
            multiplier = 1_000_000
        else:
            try:
                value = int(text.replace(".", ""))
            except ValueError:
                logger.error(f"Cannot parse {repr(raw_text)}.")
                return None
        return int(value * multiplier)

    def _getFollowersTextView(self):
        followers_text_view = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWERS_COUNT
            ),
            className=ClassName.TEXT_VIEW,
        )
        followers_text_view.wait(Timeout.MEDIUM)
        return followers_text_view

    def getFollowersCount(self) -> Optional[int]:
        followers = None
        followers_text_view = self._getFollowersTextView()
        if followers_text_view.exists():
            followers_text = followers_text_view.get_text()
            if followers_text:
                followers = self._parseCounter(followers_text)
            else:
                logger.error("Cannot get followers count text.")
        else:
            logger.error("Cannot find followers count view.")

        return followers

    def _getFollowingTextView(self):
        following_text_view = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_FOLLOWING_COUNT
            ),
            className=ClassName.TEXT_VIEW,
        )
        following_text_view.wait(Timeout.MEDIUM)
        return following_text_view

    def getFollowingCount(self) -> Optional[int]:
        following = None
        following_text_view = self._getFollowingTextView()
        if following_text_view.exists(Timeout.MEDIUM):
            following_text = following_text_view.get_text()
            if following_text:
                following = self._parseCounter(following_text)
            else:
                logger.error("Cannot get following count text.")
        else:
            logger.error("Cannot find following count view.")

        return following

    def getPostsCount(self) -> int:
        post_count_view = self.device.find(
            resourceIdMatches=case_insensitive_re(
                ResourceID.ROW_PROFILE_HEADER_TEXTVIEW_POST_COUNT
            )
        )
        if post_count_view.exists(Timeout.MEDIUM):
            count = post_count_view.get_text()
            if count is not None:
                return self._parseCounter(count)
        logger.error("Cannot get posts count text.")
        return 0

    def count_photo_in_view(self) -> Tuple[int, int]:
        """return rows filled and the number of post in the last row"""
        views = f"({ClassName.RECYCLER_VIEW}|{ClassName.VIEW})"
        grid_post = self.device.find(
            classNameMatches=views, resourceIdMatches=ResourceID.LIST
        )
        if not grid_post.exists(Timeout.MEDIUM):
            return 0, 0
        for i in range(2, 6):
            lin_layout = grid_post.child(index=i, className=ClassName.LINEAR_LAYOUT)
            if i == 5 or not lin_layout.exists():
                last_index = i - 1
                last_lin_layout = grid_post.child(index=last_index)
                for n in range(1, 4):
                    if n == 3 or not last_lin_layout.child(index=n).exists():
                        if n == 3:
                            return last_index, 0
                        else:
                            return last_index - 1, n

    def getProfileInfo(self):
        username = self.getUsername()
        posts = self.getPostsCount()
        followers = self.getFollowersCount()
        following = self.getFollowingCount()

        return username, posts, followers, following

    def getProfileBiography(self) -> str:
        biography = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_HEADER_BIO_TEXT),
            className=ClassName.TEXT_VIEW,
        )
        if biography.exists():
            biography_text = biography.get_text()
            # If the biography is very long, blabla text and end with "...more" click the bottom of the text and get the new text
            is_long_bio = re.compile(
                r"{0}$".format("… more"), flags=re.IGNORECASE
            ).search(biography_text)
            if is_long_bio is not None:
                logger.debug('Found "… more" in bio - trying to expand')
                username = self.getUsername()
                biography.click(Location.BOTTOMRIGHT)
                if username != self.getUsername():
                    logger.debug(
                        "We're not in the same page - did we click a hashtag or a tag? Go back."
                    )
                    self.device.back()
                    logger.info("Failed to expand biography - checking short view.")
                return biography.get_text()
            return biography_text
        return ""

    def getFullName(self):
        full_name_view = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_HEADER_FULL_NAME),
            className=ClassName.TEXT_VIEW,
        )
        if full_name_view.exists(Timeout.SHORT):
            fullname_text = full_name_view.get_text()
            if fullname_text is not None:
                return fullname_text
        return ""

    def isPrivateAccount(self):
        private_profile_view = self.device.find(
            resourceIdMatches=case_insensitive_re(
                [
                    ResourceID.PRIVATE_PROFILE_EMPTY_STATE,
                    ResourceID.ROW_PROFILE_HEADER_EMPTY_PROFILE_NOTICE_TITLE,
                    ResourceID.ROW_PROFILE_HEADER_EMPTY_PROFILE_NOTICE_CONTAINER,
                ]
            )
        )
        return private_profile_view.exists()

    def StoryRing(self) -> DeviceFacade.View:
        return self.device.find(
            resourceId=ResourceID.REEL_RING,
        )

    def live_marker(self) -> DeviceFacade.View:
        return self.device.find(resourceId=ResourceID.LIVE_BADGE_VIEW)

    def profileImage(self):
        return self.device.find(
            resourceId=ResourceID.ROW_PROFILE_HEADER_IMAGEVIEW,
        )

    def navigateToFollowers(self):
        logger.info("Navigate to followers.")
        followers_button = self.device.find(
            resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_FOLLOWERS_CONTAINER
        )
        if followers_button.exists(Timeout.LONG):
            followers_button.click()
            followers_tab = self.device.find(
                resourceIdMatches=ResourceID.UNIFIED_FOLLOW_LIST_TAB_LAYOUT
            ).child(textContains="Followers")
            if followers_tab.exists(Timeout.LONG):
                if not followers_tab.get_property("selected"):
                    followers_tab.click()
                return True
        else:
            logger.error("Can't find followers tab!")
            return False

    def navigateToFollowing(self):
        logger.info("Navigate to following.")
        following_button = self.device.find(
            resourceIdMatches=ResourceID.ROW_PROFILE_HEADER_FOLLOWING_CONTAINER
        )
        if following_button.exists(Timeout.LONG):
            following_button.click_retry()
            following_tab = self.device.find(
                resourceIdMatches=ResourceID.UNIFIED_FOLLOW_LIST_TAB_LAYOUT
            ).child(textContains="Following")
            if following_tab.exists(Timeout.LONG):
                if not following_tab.get_property("selected"):
                    following_tab.click()
                return True
        else:
            logger.error("Can't find following tab!")
            return False

    def navigateToMutual(self):
        logger.info("Navigate to mutual friends.")
        has_mutual = False
        follow_context = self.device.find(
            resourceIdMatches=ResourceID.PROFILE_HEADER_FOLLOW_CONTEXT_TEXT
        )
        if follow_context.exists():
            follow_context.click()
            has_mutual = True
        return has_mutual

    def swipe_to_fit_posts(self):
        """calculate the right swipe amount necessary to see 12 photos"""
        displayWidth = self.device.get_info()["displayWidth"]
        element_to_swipe_over_obj = self.device.find(
            resourceIdMatches=ResourceID.PROFILE_TABS_CONTAINER
        )
        for _ in range(2):
            if not element_to_swipe_over_obj.exists():
                UniversalActions(self.device)._swipe_points(
                    direction=Direction.DOWN, delta_y=randint(300, 350)
                )
                element_to_swipe_over_obj = self.device.find(
                    resourceIdMatches=ResourceID.PROFILE_TABS_CONTAINER
                )
                continue

            element_to_swipe_over = element_to_swipe_over_obj.get_bounds()["top"]
            try:
                bar_container = self.device.find(
                    resourceIdMatches=ResourceID.ACTION_BAR_CONTAINER
                ).get_bounds()["bottom"]

                logger.info("Scrolled down to see more posts.")
                self.device.swipe_points(
                    displayWidth / 2,
                    element_to_swipe_over,
                    displayWidth / 2,
                    bar_container,
                )
                return element_to_swipe_over - bar_container
            except Exception as e:
                logger.debug(f"Exception: {e}")
                logger.info("I'm not able to scroll down.")
                return 0
        logger.warning(
            "Maybe a private/empty profile in which check failed or after whatching stories the view moves down :S.. Skip"
        )
        return -1

    def navigateToPostsTab(self):
        self._navigateToTab(TabBarText.POSTS_CONTENT_DESC)
        return PostsGridView(self.device)

    def navigateToIgtvTab(self):
        self._navigateToTab(TabBarText.IGTV_CONTENT_DESC)
        raise Exception("Not implemented")

    def navigateToReelsTab(self):
        self._navigateToTab(TabBarText.REELS_CONTENT_DESC)
        raise Exception("Not implemented")

    def navigateToEffectsTab(self):
        self._navigateToTab(TabBarText.EFFECTS_CONTENT_DESC)
        raise Exception("Not implemented")

    def navigateToPhotosOfYouTab(self):
        self._navigateToTab(TabBarText.PHOTOS_OF_YOU_CONTENT_DESC)
        raise Exception("Not implemented")

    def _navigateToTab(self, tab: TabBarText):
        tabs_view = self.device.find(
            resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_TAB_LAYOUT),
            className=ClassName.HORIZONTAL_SCROLL_VIEW,
        )
        button = tabs_view.child(
            descriptionMatches=case_insensitive_re(tab),
            resourceIdMatches=case_insensitive_re(ResourceID.PROFILE_TAB_ICON_VIEW),
            className=ClassName.IMAGE_VIEW,
        )

        attempts = 0
        while not button.exists():
            attempts += 1
            self.device.swipe(Direction.UP, scale=0.1)
            if attempts > 2:
                logger.error(f"Cannot navigate to tab '{tab}'")
                save_crash(self.device)
                return

        button.click()

    def _getRecyclerView(self):
        views = f"({ClassName.RECYCLER_VIEW}|{ClassName.VIEW})"

        return self.device.find(classNameMatches=views)


class FollowingView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def do_unfollow_from_list(self, username, user_row=None) -> Optional[bool]:
        """
        :return: True if unfollowed, False on failure,
                 None if the account has no Unfollow option at all
        """
        exists = False
        username_row = ""
        if user_row is None:
            user_row = self.device.find(
                resourceId=ResourceID.FOLLOW_LIST_CONTAINER,
                className=ClassName.LINEAR_LAYOUT,
            )
        if user_row.exists(Timeout.MEDIUM):
            exists = True
            username_row = user_row.child(index=1).child().child().get_text()
        if not exists or username_row != username:
            logger.error(f"Cannot find {username} in following list.")
            return False

        UNFOLLOW_REGEX = "^Unfollow$"

        # Fast path: some rows show a direct "Following" button we can tap
        # straight away, instead of going through the three-dots menu.
        following_button = user_row.child(index=2, textMatches="^Following$")
        if following_button.exists(Timeout.SHORT):
            logger.debug("Direct 'Following' button found, using it.")
            following_button.click()
            random_sleep(0, 1, modulable=False)
        else:
            # new layout: unfollow is behind the three-dots menu on each row
            options_button = user_row.child(
                descriptionMatches=case_insensitive_re("options|more")
            )
            if not options_button.exists(Timeout.SHORT):
                # fallback: it's the last item on the row, after the Message/Following button
                options_button = user_row.child(index=3)
            if not options_button.exists():
                logger.error(f"Cannot find the options button for {username}.")
                save_crash(self.device)
                return False
            logger.debug("Opening the three-dots menu.")
            options_button.click()

            unfollow_row = self.device.find(
                classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
                textMatches=UNFOLLOW_REGEX,
            )
            if not unfollow_row.exists(Timeout.SHORT):
                logger.info(
                    f"@{username} has no Unfollow option. Can't unfollow from the list."
                )
                self.device.back()
                return None
            logger.debug("Pressing on Unfollow.")
            unfollow_row.click()
            random_sleep(0, 1, modulable=False)

        # private accounts ask for an extra confirmation
        confirm_unfollow_button = self.device.find(
            classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
            textMatches=UNFOLLOW_REGEX,
        )
        if confirm_unfollow_button.exists(Timeout.SHORT):
            logger.debug("Confirm unfollow private account.")
            confirm_unfollow_button.click()
            random_sleep(0, 1, modulable=False)

        UniversalActions.detect_block(self.device)
        # "Follow back" shows up for accounts that follow you: the unfollow worked
        FOLLOW_REGEX = "^Follow$|^Follow back$"
        follow_button = user_row.child(index=2, textMatches=FOLLOW_REGEX)
        if follow_button.exists(Timeout.SHORT):
            logger.info(
                f"{username} unfollowed.",
                extra={"color": f"{Style.BRIGHT}{Fore.GREEN}"},
            )
            return True
        logger.error(f"Cannot confirm unfollow for {username}.")
        save_crash(self.device)
        return False

class FollowersView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _find_user_to_remove(self, username):
        row = self.device.find(resourceId=ResourceID.FOLLOW_LIST_CONTAINER)
        return row if row.child(textMatches=username).exists() else None

    def _get_remove_button(self, row_obj):
        REMOVE_TEXT = "^Remove$"
        return row_obj.child(
            resourceId=ResourceID.BUTTON, textMatches=case_insensitive_re(REMOVE_TEXT)
        )

    def _click_button(self, obj, obj_name):
        if obj.exists(Timeout.SHORT):
            logger.info(f"Pressing on {obj_name} button.")
            obj.click()
            return True
        logger.info(f"Object {obj_name} doesn't exists. Can't press on it!")
        return False

    def _confirm_remove_follower(self):
        obj = self.device.find(resourceId=ResourceID.ACTION_SHEET_ROW_TEXT_VIEW)
        return self._click_button(obj, "remove confirmation")

    def remove_follower(self, username):
        user_row = self._find_user_to_remove(username)
        if user_row is not None and user_row.exists():
            if self._click_button(self._get_remove_button(user_row), "remove"):
                return self._confirm_remove_follower()
        return False


class CurrentStoryView:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def getStoryFrame(self) -> DeviceFacade.View:
        return self.device.find(
            resourceId=ResourceID.REEL_VIEWER_MEDIA_CONTAINER,
        )

    def getUsername(self) -> str:
        reel_viewer_title = self.device.find(
            resourceId=ResourceID.REEL_VIEWER_TITLE,
        )
        reel_exists = reel_viewer_title.exists(ignore_bug=True)
        if reel_exists == "BUG!":
            return reel_exists
        return (
            ""
            if not reel_exists
            else reel_viewer_title.get_text(error=False).replace(" ", "")
        )

    def getTimestamp(self) -> Optional[datetime.datetime]:
        reel_viewer_timestamp = self.device.find(
            resourceId=ResourceID.REEL_VIEWER_TIMESTAMP,
        )
        if reel_viewer_timestamp.exists():
            timestamp = reel_viewer_timestamp.get_text().strip()
            value = int(re.sub("[^0-9]", "", timestamp))
            if timestamp[-1] == "s":
                return datetime.timestamp(
                    datetime.datetime.now() - datetime.timedelta(seconds=value)
                )
            elif timestamp[-1] == "m":
                return datetime.timestamp(
                    datetime.datetime.now() - datetime.timedelta(minutes=value)
                )
            elif timestamp[-1] == "h":
                return datetime.timestamp(
                    datetime.datetime.now() - datetime.timedelta(hours=value)
                )
            else:
                return datetime.timestamp(
                    datetime.datetime.now() - datetime.timedelta(days=value)
                )
        return None


class UniversalActions:
    def __init__(self, device: DeviceFacade):
        self.device = device

    def _swipe_points(
        self,
        direction: Direction,
        start_point_x=-1,
        start_point_y=-1,
        delta_x=-1,
        delta_y=450,
    ) -> None:
        displayWidth = self.device.get_info()["displayWidth"]
        displayHeight = self.device.get_info()["displayHeight"]
        middle_point_x = displayWidth / 2
        if start_point_y == -1:
            start_point_y = displayHeight / 2
        if direction == Direction.UP:
            if start_point_y + delta_y > displayHeight:
                delta = start_point_y + delta_y - displayHeight
                start_point_y = start_point_y - delta
            self.device.swipe_points(
                middle_point_x,
                start_point_y,
                middle_point_x,
                start_point_y + delta_y,
            )
        elif direction == Direction.DOWN:
            if start_point_y - delta_y < 0:
                delta = abs(start_point_y - delta_y)
                start_point_y = start_point_y + delta
            self.device.swipe_points(
                middle_point_x,
                start_point_y,
                middle_point_x,
                start_point_y - delta_y,
            )
        elif direction == Direction.LEFT:
            if start_point_x == -1:
                start_point_x = displayWidth * 2 / 3
            if delta_x == -1:
                delta_x = uniform(0.95, 1.25) * (displayWidth / 2)
            self.device.swipe_points(
                start_point_x,
                start_point_y,
                start_point_x - delta_x,
                start_point_y,
            )

    def press_button_back(self) -> None:
        back_button = self.device.find(
            resourceIdMatches=ResourceID.ACTION_BAR_BUTTON_BACK
        )
        if back_button.exists():
            logger.info("Pressing on back button.")
            back_button.click()

    def _reload_page(self) -> None:
        logger.debug("Reload page.")
        self._swipe_points(direction=Direction.UP)
        random_sleep(inf=5, sup=8, modulable=False)

    @staticmethod
    def detect_block(device) -> bool:
        if not args.disable_block_detection:
            return False
        logger.debug("Checking for block...")
        if "blocked" in device.deviceV2.toast.get_message(1.0, 2.0, default=""):
            logger.warning("Toast detected!")
        serius_block = device.find(
            className=ClassName.IMAGE,
            textMatches=case_insensitive_re("Force reset password icon"),
        )
        if serius_block.exists():
            raise ActionBlockedError("Serius block detected :(")
        block_dialog = device.find(
            resourceIdMatches=ResourceID.BLOCK_POPUP,
        )
        popup_body = device.find(
            resourceIdMatches=ResourceID.IGDS_HEADLINE_BODY,
        )
        popup_appears = block_dialog.exists()
        if popup_appears:
            if popup_body.exists():
                regex = r".+deleted"
                is_post_deleted = re.match(regex, popup_body.get_text(), re.IGNORECASE)
                if is_post_deleted:
                    logger.info(f"{is_post_deleted.group()}")
                    logger.debug("Click on OK button.")
                    device.find(
                        resourceIdMatches=ResourceID.NEGATIVE_BUTTON,
                    ).click()
                    is_blocked = False
                else:
                    is_blocked = True
            else:
                is_blocked = True
        else:
            is_blocked = False

        if is_blocked:
            logger.error("Probably block dialog is shown.")
            raise ActionBlockedError(
                "Seems that action is blocked. Consider reinstalling Instagram app and be more careful with limits!"
            )

    def _check_if_no_posts(self) -> bool:
        obj = self.device.find(resourceId=ResourceID.IGDS_HEADLINE_EMPHASIZED_HEADLINE)
        return obj.exists(Timeout.MEDIUM)

    def search_text(self, username):
        search_row = self.device.find(resourceId=ResourceID.ROW_SEARCH_EDIT_TEXT)
        if search_row.exists(Timeout.MEDIUM):
            search_row.set_text(username, Mode.PASTE if args.dont_type else Mode.TYPE)
            return True
        else:
            return False

    @staticmethod
    def close_keyboard(device):
        flag = DeviceFacade(device.device_id, device.app_id)._is_keyboard_show()
        if flag:
            logger.debug("The keyboard is currently open. Press back to close.")
            device.back()
        elif flag is None:
            tabbar_container = device.find(
                resourceId=ResourceID.FIXED_TABBAR_TABS_CONTAINER
            )
            if tabbar_container.exists():
                delta = tabbar_container.get_bounds()["bottom"]
            else:
                delta = 375
            logger.debug(
                "Failed to check if keyboard is open! Will do a little swipe up to prevent errors."
            )
            UniversalActions(device)._swipe_points(
                direction=Direction.UP,
                start_point_y=randint(delta + 10, delta + 150),
                delta_y=randint(50, 100),
            )
