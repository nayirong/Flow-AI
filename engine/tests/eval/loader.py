"""
TestCaseLoader: Loads test cases from YAML files and Supabase.

Merges both sources, applies filters, deduplicates by test_name.
If duplicate test_name exists, Supabase wins (allows override).
"""

from typing import List, Optional


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
        yaml_base_path: str,
        eval_supabase_client,  # AsyncClient
    ):
        """Initialize loader with paths and DB client."""
        self.yaml_base_path = yaml_base_path
        self.eval_supabase_client = eval_supabase_client
    
    async def load_test_cases(
        self,
        client_id: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        test_name: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List:  # -> list[TestCase]
        """
        Load and merge test cases from YAML + Supabase, apply filters.
        
        Returns:
            List of TestCase objects, deduplicated by test_name
            (Supabase overrides YAML if duplicate).
        """
        # TODO: implement
        # - Load YAML cases via _load_yaml_cases()
        # - Load Supabase cases via _load_supabase_cases()
        # - Merge via _merge_cases()
        # - Apply filters via _apply_filters()
        # - Return filtered list
        
        raise NotImplementedError("TestCaseLoader.load_test_cases() not yet implemented")
    
    async def _load_yaml_cases(self) -> List:  # -> list[TestCase]
        """Load all YAML files from cases/ directory tree."""
        # TODO: implement
        # - Walk yaml_base_path directory tree
        # - Load each .yaml file
        # - Parse into TestCase objects
        # - Log warning and skip on parse error
        # - Return list
        raise NotImplementedError()
    
    async def _load_supabase_cases(self) -> List:  # -> list[TestCase]
        """Query eval_test_cases table where enabled=TRUE."""
        # TODO: implement
        # - Query Supabase eval_test_cases table
        # - Filter by enabled=TRUE
        # - Parse into TestCase objects
        # - Return list
        raise NotImplementedError()
    
    def _merge_cases(
        self,
        yaml_cases: List,  # list[TestCase]
        db_cases: List,  # list[TestCase]
    ) -> List:  # -> list[TestCase]
        """
        Merge sources, deduplicate by test_name.
        If duplicate, Supabase wins (allows override).
        """
        # TODO: implement
        # - Create dict keyed by test_name
        # - Add YAML cases first
        # - Overwrite with DB cases (DB wins)
        # - Return list of values
        raise NotImplementedError()
    
    def _apply_filters(
        self,
        cases: List,  # list[TestCase]
        **filters,
    ) -> List:  # -> list[TestCase]
        """Apply client_id, category, priority, tags, test_name filters."""
        # TODO: implement filtering logic
        raise NotImplementedError()
