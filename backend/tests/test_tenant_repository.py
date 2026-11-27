from app.repositories.supabase_repository import _TenantBuilder, _execute


class FakeBuilder:
    def __init__(self):
        self.filters = []
        self.payload = None

    def select(self, *args, **kwargs):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def delete(self):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        return self


def test_tenant_repository_filters_reads_and_mutations_and_sets_owner_on_insert():
    company_id = "30000000-0000-4000-8000-000000000001"
    select = FakeBuilder()
    _execute(_TenantBuilder(select, "devices", company_id).select("*"))
    assert select.filters == [("company_id", company_id)]

    update = FakeBuilder()
    _execute(_TenantBuilder(update, "devices", company_id).update({"hostname": "router"}))
    assert update.filters == [("company_id", company_id)]
    assert update.payload == {"hostname": "router", "company_id": company_id}

    insert = FakeBuilder()
    _execute(_TenantBuilder(insert, "devices", company_id).insert({"hostname": "router"}))
    assert insert.filters == []
    assert insert.payload == {"hostname": "router", "company_id": company_id}
