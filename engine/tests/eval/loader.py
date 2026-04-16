"""
TestCaseLoader: Loads test cases from YAML files and Supabase.

Merges both sources, applies filters, deduplicates by test_name.
If duplicate test_name exists, Supabase wins (allows override).
"""

import os
import yaml
import logging
from pathlib import Path
from typing import List, Optional

from .models import TestCase


logger = logging.getLogger(__name__)


class TestCaseLoader:
    """
    Loads and filters test cases from YAML + Supabase.
    
    Sources:
    - YAML files in engine/tests/eval/cases/
    - Supabase eval_test_cases table
    
    Merge strategy:
    - Deduplicate by test_name
    - Supabase wins on conflict (allows runtime override)
    """
    
    def __init__(
        self,
        eval_supabase_client,  # AsyncClient
        cases_dir: Optional[Path] = None,
    ):
        """Initialize loader with paths and DB client."""
        self.eval_supabase_client = eval_supabase_client
        self.cases_dir = cases_dir or Path(__file__).parent / "cases"
    
    async def load(
        self,
        client_id: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        test_name: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[TestCase]:
        """
        Load and merge test cases from YAML + Supabase, apply filters.
        
        Returns:
            List of TestCase objects, deduplicated by test_name
            (YAML takes precedence if duplicate).
        """
        try:
            # Load from both sources
            yaml_cases = self._load_yaml_cases()
            db_cases = await self._load_supabase_cases()
            
            # Merge (YAML takes precedence per task spec)
            merged = self._merge_cases(yaml_cases, db_cases)
            
            # Apply filters
            filtered = self._apply_filters(
                merged,
                client_id=client_id,
                category=category,
                priority=priority,
                tags=tags,
                test_name=test_name,
                enabled_only=enabled_only
            )
            
            return filtered
        
        except Exception as e:
            logger.error(f"TestCaseLoader.load() failed: {e}")
            return []
    
    def _load_yaml_cases(self) -> List[TestCase]:
        """Load all YAML files from cases/ directory tree."""
        cases = []
        
        try:
            if not self.cases_dir.exists():
                logger.warning(f"Cases directory does not exist: {self.cases_dir}")
                return cases
            
            # Walk directory tree
            for yaml_file in self.cases_dir.rglob("*.yaml"):
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)
                    
                    # Handle both single test case and list of test cases
                    if isinstance(data, list):
                        for item in data:
                            try:
                                cases.append(TestCase(**item))
                            except Exception as e:
                                logger.warning(f"Invalid test case in {yaml_file}: {e}")
                    elif isinstance(data, dict):
                        try:
                            cases.append(TestCase(**data))
                        except Exception as e:
                            logger.warning(f"Invalid test case in {yaml_file}: {e}")
                
                except Exception as e:
                    logger.warning(f"Failed to load YAML file {yaml_file}: {e}")
        
        except Exception as e:
            logger.error(f"_load_yaml_cases() failed: {e}")
        
        return cases
    
    async def _load_supabase_cases(self) -> List[TestCase]:
        """Query eval_test_cases table where enabled=TRUE."""
        try:
            result = await self.eval_supabase_client.table("eval_test_cases").select("*").execute()
            rows = result.data or []
            cases = []
            for row in rows:
                try:
                    cases.append(TestCase(**row))
                except Exception as e:
                    logger.warning(f"Skipping invalid Supabase row (id={row.get('id')}): {e}")
            return cases
        except Exception as e:
            logger.error(f"_load_supabase_cases() failed: {e}")
            return []
    
    def _merge_cases(
        self,
        yaml_cases: List[TestCase],
        db_cases: List[TestCase],
    ) -> List[TestCase]:
        """
        Merge sources, deduplicate by test_name.
        If duplicate, YAML takes precedence (per task spec).
        """
        # Use dict to deduplicate by test_name
        cases_dict = {}
        
        # Add DB cases first
        for case in db_cases:
            cases_dict[case.test_name] = case
        
        # Overwrite with YAML cases (YAML wins)
        for case in yaml_cases:
            cases_dict[case.test_name] = case
        
        return list(cases_dict.values())
    
    def _apply_filters(
        self,
        cases: List[TestCase],
        client_id: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        test_name: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[TestCase]:
        """Apply client_id, category, priority, tags, test_name filters."""
        filtered = cases
        
        # Filter by enabled
        if enabled_only:
            filtered = [c for c in filtered if c.enabled]
        
        # Filter by client_id
        if client_id:
            filtered = [c for c in filtered if c.client_id == client_id]
        
        # Filter by category
        if category:
            filtered = [c for c in filtered if c.category == category]
        
        # Filter by priority
        if priority:
            filtered = [c for c in filtered if c.priority == priority]
        
        # Filter by tags (any tag match)
        if tags:
            filtered = [c for c in filtered if any(tag in c.tags for tag in tags)]
        
        # Filter by test_name (exact match)
        if test_name:
            filtered = [c for c in filtered if c.test_name == test_name]
        
        return filtered
