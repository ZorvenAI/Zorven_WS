"""Tests for HierarchyBuilder logic module."""

import pytest

from app.logic.hierarchy_builder import HierarchyBuilder


@pytest.fixture
def builder():
    return HierarchyBuilder()


class TestHierarchyBuilder:

    async def test_build_calculates_depth(self, builder):
        llm_result = {
            "hierarchy": {
                "root": {
                    "name": "Parent",
                    "type": "master",
                    "children": [
                        {
                            "name": "Child1",
                            "type": "sub_brand",
                            "children": [
                                {
                                    "name": "Grandchild",
                                    "type": "product_line",
                                    "children": [],
                                },
                            ],
                        },
                        {
                            "name": "Child2",
                            "type": "endorsed",
                            "children": [],
                        },
                    ],
                }
            }
        }
        result = await builder.build(llm_result)
        assert result["total_depth"] == 3
        assert result["total_nodes"] == 4

    async def test_build_empty_hierarchy(self, builder):
        result = await builder.build({})
        assert result["total_depth"] == 0
        assert result["total_nodes"] == 0

    async def test_build_single_root(self, builder):
        llm_result = {
            "hierarchy": {
                "root": {
                    "name": "Single",
                    "type": "master",
                    "children": [],
                }
            }
        }
        result = await builder.build(llm_result)
        assert result["total_depth"] == 1
        assert result["total_nodes"] == 1
