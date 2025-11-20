import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class AirtableHtmlParser:
    """Class to extract column details and old/new values from Airtable's row activity diffRowHtml."""

    def __init__(self, html):
        self.html = html
        self.soup = BeautifulSoup(html, "html.parser")
        self.column_id = None
        self.column_name = None
        self.column_type = None
        self.old_values = []
        self.new_values = []

    def _extract_metadata(self):
        """Extracts Column Name, ID, and Type from the container."""
        container = self.soup.select_one('.historicalCellContainer')
        if container:
            header_div = container.select_one('.micro.strong.caps')
            if header_div:
                self.column_name = header_div.get_text(strip=True)
                self.column_id = header_div.get('columnid')
            
            cell_value_div = container.select_one('.historicalCellValue')
            if cell_value_div:
                self.column_type = cell_value_div.get('data-columntype')
        
        if not self.column_type:
            logger.debug("Could not determine column type for HTML diff.")
            return False
        return True

    def _parse_simple_text_fields(self):
        """Parses Text, Number, Date, Phone fields."""
        
        # --- Extract Old Value (Removed) ---
        removed_text_blocks = self.soup.select(
            '.historicalCellValue [class*="colors-background-negative"],'
            '.historicalCellValue [class*="colors-foreground-accent-negative"],'
            '.historicalCellValue [class*="strikethrough"]'
        )
        for rec in removed_text_blocks:
            val = rec.get_text(strip=True)
            if val: self.old_values.append(val)
        
        # --- Extract New Value (Added) ---
        added_text_blocks = self.soup.select('.historicalCellValue [class*="colors-background-success"]')
        for rec in added_text_blocks:
            val = rec.get_text(strip=True)
            if val: self.new_values.append(val.strip())

    def _parse_select_fields(self):
        """Parses Single Select and Multi Select fields."""
        
        # --- Extract Old Value (Removed) ---
        removed_by_style = self.soup.select('.choiceToken[style*="line-through"]')
        for pill in removed_by_style:
            self.old_values.append(pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True))

        # --- Extract New Value (Added/Retained) ---
        active_pills = self.soup.select('.choiceToken:not([style*="line-through"])')
        for pill in active_pills:
            text = pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True)
            next_sibling = pill.find_next_sibling('div')
            # Mark as added if the sibling contains the plus icon SVG
            if next_sibling and next_sibling.select_one('svg use[href*="#Plus"]'):
                self.new_values.append(f"{text} +")
            else:
                self.new_values.append(text)

    def _parse_checkbox_field(self):
        """Parses Checkbox fields."""
        if self.soup.select_one('.historicalCellValue .redLight2'):
            self.old_values.append("True")
        if self.soup.select_one('.historicalCellValue .greenLight2'):
            self.new_values.append("True")

    def _parse_attachment_field(self):
        """Parses Multiple Attachment fields."""
        removed_attachments = self.soup.select('.preview[title*="was removed"], .preview.rounded[class*="border-red-light1"]')
        for att in removed_attachments:
            val = att.get('title')
            if val and val.endswith(" was removed"):
                self.old_values.append(val[:-12])

        added_attachments = self.soup.select('.preview[title*="was added"], .preview.rounded[class*="border-green-light1"]')
        for att in added_attachments:
            val = att.get('title')
            if val and val.endswith(" was added"):
                self.new_values.append(val[:-10])

    def _parse_rating_field(self):
        """Parses Rating fields."""
        # Removed rating has negative background
        rating_container_old = self.soup.select_one('.ratingContainer[class*="colors-background-negative"]')
        if rating_container_old:
            count = len(rating_container_old.select('svg:not(.invisible) path[fill]'))
            if count > 0: self.old_values.append(str(count))

        # Added/New rating has success background or is the final state
        rating_container_new = self.soup.select_one('.ratingContainer[class*="colors-background-success"]') or self.soup.select_one('.ratingContainer:not([class*="colors-background-negative"])')
        if rating_container_new:
            count = len(rating_container_new.select('svg:not(.invisible) path[fill]'))
            if count > 0: self.new_values.append(str(count))

    def _parse_foreign_key_field(self):
        """Parses Foreign key field."""
        
        # --- Extract Old Value (Removed) ---
        removed = self.soup.select('.historicalCellValue .foreignRecord.removed')
        for rec in removed:
            self.old_values.append(rec.get('title') or rec.get_text(strip=True))

         # --- Extract New Value (Added) ---
        added = self.soup.select('.historicalCellValue .foreignRecord.added')
        for rec in added:
            self.new_values.append(rec.get('title') or rec.get_text(strip=True))
       
    def parse_diff(self):
        """
        Orchestrates the parsing based on column type and returns the final result.
        """
        if not self._extract_metadata():
            return {
                "columnId": self.column_id, "columnName": self.column_name,
                "columnType": None, "oldValue": None, "newValue": None
            }

        # Dispatch parsing based on column type
        if self.column_type in ('text', 'multilineText', 'phone', 'number', 'date', 'currency', 'percent'):
            self._parse_simple_text_fields()
        elif self.column_type in ('select', 'multiSelect'):
            self._parse_select_fields()
        elif self.column_type == 'checkbox':
            self._parse_checkbox_field()
        elif self.column_type == 'multipleAttachment':
            self._parse_attachment_field()
        elif self.column_type == 'rating':
            self._parse_rating_field()
        elif self.column_type == 'foreignKey':
            self._parse_foreign_key_field()
        
        # --- Final Formatting ---
        if self.column_type in ('multiSelect', 'multipleAttachment', 'foreignKey'):
            old_val = " | ".join(sorted(list(set(filter(None, self.old_values))))) or None
            new_val = " | ".join(sorted(list(set(filter(None, self.new_values))))) or None
        else:
            old_val = self.old_values[0] if self.old_values else None
            new_val = self.new_values[0] if self.new_values else None

        # Fallback for simple changes 
        if not old_val and not new_val:
            diff_container = self.soup.select_one('.historicalCellValue')
            if diff_container:
                old_el = diff_container.select_one('[class*="strikethrough"]')
                new_el = diff_container.select_one(':not([class*="strikethrough"]) > .flex-auto')
                old_val = old_el.get_text(strip=True) if old_el else None
                new_val = new_el.get_text(strip=True) if new_el else None
        
        return {
            "columnId": self.column_id,
            "columnName": self.column_name,
            "columnType": self.column_type,
            "oldValue": old_val,
            "newValue": new_val
        }