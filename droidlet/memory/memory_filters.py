"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from typing import List
import torch
from droidlet.memory.filters_conversions import get_inequality_symbol, sqly_to_new_filters

SELFID = "0" * 32


def maybe_and(sql, a):
    if a:
        return sql + " AND "
    else:
        return sql


def maybe_or(sql, a):
    if a:
        return sql + " OR "
    else:
        return sql


# FIXME merge this with more general filters
# FIXME don't just pick the first one, allow all props returned
def get_property_value(agent_memory, mem, prop, get_all=False):
    """
    Tries to get property value from a memory.

    Args:
        agent_memory: an AgentMemory object
        mem: a MemoryNode object or memid (str)
        prop: a string with the name of the property

    looks with the following order of precedence:
    1: main memory table
    2: table corresponding to the nodes .TABLE
    3: triple with the nodes memid as subject and prop as predicate
    """
    # TODO maybe don't do this? esp if there are a lot of mems and we don't need to?
    # just need the MemoryNode for the Table anyway
    if type(mem) is str:
        mem = agent_memory.get_mem_by_id(mem)

    # is it in the main memory table?
    cols = [c[1] for c in agent_memory._db_read("PRAGMA table_info(Memories)")]
    if prop in cols:
        cmd = "SELECT " + prop + " FROM Memories WHERE uuid=?"
        r = agent_memory._db_read(cmd, mem.memid)
        return r[0][0]
    # is it in the mem.TABLE?
    T = mem.TABLE
    cols = [c[1] for c in agent_memory._db_read("PRAGMA table_info({})".format(T))]
    if prop in cols:
        cmd = "SELECT " + prop + " FROM " + T + " WHERE uuid=?"
        r = agent_memory._db_read(cmd, mem.memid)
        return r[0][0]
    # is it a triple?
    triples = agent_memory.get_triples(subj=mem.memid, pred_text=prop, return_obj_text="always")
    if len(triples) > 0:
        if get_all:
            return [t[2] for t in triples]
        else:
            return triples[0][2]

    return None


def search_by_property(agent_memory, prop, value, comparison_symbol, memtype):
    """
    Tries to find memories with a property value

    Args:
        agent_memory: an AgentMemory object
        prop: a string with the name of the property
        value: the value to match.  if comparison_symbol is <>,
            should be a tuple of (low, high); and if comparison symbol is
            "%", should be a tuple of (modulus, remainder)
            otherwise value should be a singleton tuple
        comparison_symbol: one of "=", "<", "<=", ">", ">=", "%", "<>"
        memtype: a memory type

    returns a list of memids

    looks with the following order of precedence:
    1: main memory table
    2: table corresponding to the nodes .TABLE
    3: triple with the nodes memid as subject and prop as predicate
    """
    try:
        if comparison_symbol != "%" or comparison_symbol != "<>":
            assert len(value) == 1
        else:
            assert len(value) == 2
    except:
        raise Exception(
            "comparison symbol in basic search is {} but value is {}".format(
                comparison_symbol, value
            )
        )

    if comparison_symbol == "%":
        where = "WHERE " + prop + " % " + str(value[0]) + " =?"
        v = value[1]
    elif comparison_symbol == "<>":
        where = "WHERE " + prop + ">? AND " + prop + "<?"
        v = value
    else:
        where = "WHERE " + prop + comparison_symbol + "?"
        v = value

    # is it in the main memory table?
    cols = [c[1] for c in agent_memory._db_read("PRAGMA table_info(Memories)")]
    if prop in cols:
        cmd = "SELECT uuid FROM Memories " + where
        return [m[0] for m in agent_memory._db_read(cmd, *v)]

    # is it in the node table?
    T = agent_memory.nodes[memtype].TABLE
    cols = [c[1] for c in agent_memory._db_read("PRAGMA table_info({})".format(T))]
    if prop in cols:
        cmd = "SELECT uuid FROM " + T + " " + where
        return [m[0] for m in agent_memory._db_read(cmd, *v)]

    # is it a triple?
    # n.b. if the query is about an actual triple (e.g. SELECT subj FROM Triples ...), it would have been
    # handled in the previous block.  this block is for e.g. "SELECT MEMORY FROM ReferenceObjects WHERE ..."
    # and where the WHERE clause uses a "column name" that is a triple

    # FIXME! it is assumed for now that the value is the obj_text, not the obj; need to
    # to introduce special comparison_symbol for the obj memid case
    if comparison_symbol != "=" and comparison_symbol != "=#=":
        raise Exception("Triple values need to have '=' or '=#=' as comparison symbol for now")
    if comparison_symbol == "=":
        triples = agent_memory.get_triples(pred_text=prop, obj_text=value[0])
    else:
        triples = agent_memory.get_triples(pred_text=prop, obj=value[0])

    node_children = agent_memory.node_children[memtype]
    if len(triples) > 0:
        return [t[0] for t in triples if agent_memory.get_node_from_memid(t[0]) in node_children]
    return []


def try_float(value, where_clause):
    try:
        return float(value)
    except:
        raise Exception("tried to get float from {} in {}".format(value, where_clause))


def argval_subsample_idx(values, n, polarity="MAX"):
    """ values is a list, n an int, polarity is MAX or MIN"""
    assert n > 0
    descending = {"MAX": True, "MIN": False}[polarity]
    _, idxs = torch.sort(torch.Tensor(values), descending=descending)
    return idxs.tolist()[:n]


def random_subsample_idx(num_mems, n, same="DISALLOWED"):
    if num_mems == 0:
        return []
    if same == "REQUIRED":
        return [torch.randint(num_mems, (1,)).item()] * n
    replace = True
    if same == "DISALLOWED":
        replace = False
        if n > num_mems:
            raise Exception(
                "RANDOM selection supposed to return {} memories withour replacement but only got {}".format(
                    n, num_mems
                )
            )
    return torch.multinomial(torch.ones(num_mems), n, replacement=replace).tolist()


class MemorySearcher:
    """ 
    Basic string form:

    SELECT <attribute>;
    FROM mem_type(s);
    WHERE <sentence of clauses>;
    ORDER BY <attribute>; 
    LIMIT <ordinal> DESC/ASC;
    SAME ALLOWED/DISALLOWED/REQUIRED;
    CONTAINS_COREFERENCE ;

    for now it assumed that every <attribute> is an explicitly stored property of the memory. 
    the SELECT clause can have value "COUNT" or "MEMORY" or an attribute.
    the FROM clause is a MemoryNode NodeType (TODO sentence with OR's)
    the WHERE clause is a sentence of the recursive form 
        (clause, CONJUNCTION  ... CONJUCTION clause), where each CONJUCTION is either AND or OR
        or a sentence of the form (NOT clause).  at a given level of the sentence, all conjuctions
        should be the same. 
    the ORDER BY clause can be RANDOM or an explicitly stored property
        while the language allows a LOCATION clause, this searcher cannot handle it
    the LIMIT is a positive integer
    
    basic dict form has keys:
    "output": corresponding to the "SELECT" clause; with string values "COUNT" or "MEMORY"
        or attribute dict as possible values
    "memory_type": corresponding to "FROM"
    "where_clause":  a tree of dicts where sentences (lists)
        of clauses are keyed by a conjunction
    "selector": corresponding to "ORDER BY", "LIMIT", "SAME"
    "contains_coreference": corresponding to "CONTAINS_COREFERENCE"

    the search method takes an agent_memory as input, and either a query 
    (or this object was initialized with a query) as a kw arg
    and outputs a list of MemoryNodes and corresponding list of values.
    if the output type/SELECT is COUNT, the list of values will be the count repeated for each memory
    if the output type is MEMORY, the list of values will be a None for each memory
    
    """

    # TODO eventually allow any attribute- if its not a "simple" attribute,
    #  pass in as attribute object (callable with proper signature)

    def __init__(self, self_memid=SELFID, query=None):
        self.self_memid = self_memid
        self.query = query

    def maybe_convert_query(self, query):
        if type(query) is str:
            return sqly_to_new_filters(query)
        else:
            return query

    def handle_where(self, agent_memory, where_clause, memtype):
        # do this brutally for now, if we need can make more efficient
        if where_clause.get("AND"):
            memid_lists = []
            for c in where_clause["AND"]:
                memid_lists.append(self.handle_where(agent_memory, c, memtype))
            return set.intersection(*[set(m) for m in memid_lists])
        if where_clause.get("OR"):
            memid_lists = []
            for c in where_clause["OR"]:
                memid_lists.append(self.handle_where(agent_memory, c, memtype))
            return set.union(*[set(m) for m in memid_lists])
        if where_clause.get("NOT"):
            # FIXME memtype might be a union of node types
            # maybe FIXME? don't retrieve everything until necessary
            memtypes = agent_memory.node_children[memtype]
            node_type_clause = ("OR node_type=? " * len(memtypes))[3:-1]
            all_memids = agent_memory._db_read(
                "SELECT uuid FROM Memories WHERE " + node_type_clause, *memtypes
            )
            all_memids = set([m[0] for m in all_memids])
            memids = self.handle_where(agent_memory, where_clause["NOT"][0], memtype)
            return list(all_memids - set(memids))

        if where_clause.get("input_left"):
            # this is a leaf, actually search:
            input_left = where_clause["input_left"]["value_extractor"]
            input_right = where_clause["input_right"]["value_extractor"]
            if type(input_left) is dict or type(input_right) is dict:
                raise Exception(
                    "currently search assumes attributes are explicitly stored property of the memory: {}".format(
                        where_clause
                    )
                )
            ctype = where_clause.get("comparison_type", "EQUAL")
            comparison_symbol = get_inequality_symbol(ctype)
            # FIXME do close tolerance for modulus
            if type(ctype) is dict and ctype.get("close_tolerance"):
                comparison_symbol = "<>"
                v = try_float(input_right, where_clause)
                value = (v - ctype["close_tolerance"], v + ctype["close_tolerance"])
            elif comparison_symbol[0] == "<" or comparison_symbol[0] == ">":
                # going to convert back to str later, doing this for data sanitation/debugging
                value = (try_float(input_right, where_clause),)
            elif type(ctype) is dict and ctype.get("modulus"):
                comparison_symbol = "%"
                value = (ctype["modulus"], input_right)
            else:
                value = (input_right,)
            return search_by_property(agent_memory, input_left, value, comparison_symbol, memtype)

    def handle_selector(self, agent_memory, query, memids):
        if query.get("selector"):
            selector_d = query["selector"]
            if selector_d.get("location"):
                raise Exception(
                    "queries with location selectors not yet implemented in basic search: query={}".format(
                        query
                    )
                )
            ordinal = int(selector_d.get("ordinal", 1))
            return_q = selector_d.get("return_quantity")
            if not return_q:
                raise Exception("selector subdict with no return_quantity: query={}".format(query))
            if return_q == "random":
                same = selector_d.get("same", "DISALLOWED")
                idxs = random_subsample_idx(len(memids), ordinal, same=same)
            elif type(return_q) is dict and return_q.get("argval"):
                try:
                    attribute_name = return_q["argval"]["quantity"]["attribute"]
                except:
                    raise Exception(
                        "malformed selector return quantity clause: {}".format(return_q)
                    )
                if type(attribute_name) is not str:
                    raise Exception(
                        "selector return quantity in basic search should be simple property, instead got: {}".format(
                            attribute_name
                        )
                    )
                vals = [get_property_value(agent_memory, m, attribute_name) for m in memids]
                idxs = argval_subsample_idx(
                    vals, ordinal, polarity=return_q["argval"].get("polarity", "MAX")
                )
            return [memids[i] for i in idxs]
        else:
            return memids

    def handle_output(self, agent_memory, query, memids):
        output = query.get("output", "MEMORY")
        if output == "MEMORY":
            return [agent_memory.get_mem_by_id(m) for m in memids]
        elif output == "COUNT":
            return [len(memids)] * len(memids)
        else:
            if type(output) is dict:
                try:
                    attribute_name_list = [output["attribute"]]
                except:
                    raise Exception("malformed output clause: {}".format(query))
            elif type(output) is list:
                try:
                    attribute_name_list = [a["attribute"] for a in output]
                except:
                    raise Exception("malformed output clause: {}".format(query))
            values_dict = {m: [] for m in memids}
            for aname in attribute_name_list:
                if type(aname) is not str:
                    raise Exception(
                        "output attribute in basic search should be (list of) simple properties, instead got: {}".format(
                            attribute_name_list
                        )
                    )
                for m in memids:
                    values_dict[m].append(get_property_value(agent_memory, m, aname))
            if len(attribute_name_list) == 1:
                for m in values_dict:
                    values_dict[m] = values_dict[m][0]
            # TODO switch everything to dicts
            return [values_dict[m] for m in memids]

    def search(self, agent_memory, query=None, default_memtype="ReferenceObject"):
        # returns a list of memids and accompanying values
        # TODO values are MemoryNodes when query is SELECT MEMORIES
        query = query or self.query
        if not query:
            return [], []
        query = self.maybe_convert_query(query)
        # TODO/FIXME memtype all
        memtype = query.get("memory_type", default_memtype)
        if query.get("where_clause"):
            memids = self.handle_where(agent_memory, query["where_clause"], memtype)
        else:
            memids = []
        memids = self.handle_selector(agent_memory, query, memids)
        # TODO/FIXME switch output format to dicts
        return memids, self.handle_output(agent_memory, query, memids)


# TODO?  merge into Memory
class BasicMemorySearcher:
    def __init__(self, self_memid=SELFID, search_data=None):
        self.self_memid = self_memid
        self.search_data = search_data

    def is_filter_empty(self, search_data):
        r = search_data.get("special")
        if r and len(r) > 0:
            return False
        r = search_data.get("base_range")
        if r and len(r) > 0:
            return False
        r = search_data.get("base_exact")
        if r and len(r) > 0:
            return False
        r = search_data.get("memories_range")
        if r and len(r) > 0:
            return False
        r = search_data.get("memories_exact")
        if r and len(r) > 0:
            return False
        t = search_data.get("triples")
        if t and len(t) > 0:
            return False
        return True

    def range_queries(self, r, table, a=False):
        """this does x, y, z, pitch, yaw, etc.
        input format for generates is
        {"xmin": float, xmax: float, ... , yawmin: float, yawmax: float}
        """
        sql = ""
        vals = []
        for k, v in r.items():
            if "min" in k:
                sql = maybe_and(sql, len(vals) > 0)
                sql += table + "." + k.replace("min", "") + ">? "
                vals.append(v)
            if "max" in k:
                sql = maybe_and(sql, len(vals) > 0)
                sql += table + "." + k.replace("max", "") + "<? "
                vals.append(v)
        return sql, vals

    def exact_matches(self, m, table, a=False):
        sql = ""
        vals = []
        for k, v in m.items():
            sql = maybe_and(sql, len(vals) > 0)
            sql += table + "." + k + "=? "
            vals.append(v)
        return sql, vals

    def triples(self, triples, table, a=False):
        # currently does an "and": the memory needs to satisfy all triples
        vals = []
        if not triples:
            return "", vals
        sql = "{}.uuid IN (SELECT subj FROM Triples WHERE ".format(table)
        for t in triples:
            sql = maybe_or(sql, len(vals) > 0)
            if t.get("pred_text"):
                vals.append(t["pred_text"])
                if t.get("obj_text"):
                    sql += "(pred_text, obj_text)=(?, ?)"
                    vals.append(t["obj_text"])
                else:
                    sql += "(pred_text, obj)=(?, ?)"
                    vals.append(t["obj"])
            else:
                if t.get("obj_text"):
                    sql += "obj_text=?"
                    vals.append(t["obj_text"])
                else:
                    sql += "obj=?"
                    vals.append(t["obj"])
        sql += " GROUP BY subj HAVING COUNT(subj)=? )"
        vals.append(len(triples))
        return sql, vals

    def get_query(self, search_data, ignore_self=True):
        table = search_data["base_table"]
        if self.is_filter_empty(search_data):
            query = "SELECT uuid FROM " + table
            if ignore_self:
                query += " WHERE uuid !=?"
                return query, [self.self_memid]
            else:
                return query, []

        query = (
            "SELECT {}.uuid FROM {}"
            " INNER JOIN Memories as M on M.uuid={}.uuid"
            " WHERE ".format(table, table, table)
        )

        args = []
        fragment, vals = self.range_queries(search_data.get("base_range", {}), table)
        query = maybe_and(query, len(args) > 0)
        args.extend(vals)
        query += fragment

        fragment, vals = self.exact_matches(search_data.get("base_exact", {}), table)
        query = maybe_and(query, len(args) > 0 and len(vals) > 0)
        args.extend(vals)
        query += fragment

        fragment, vals = self.range_queries(search_data.get("memories_range", {}), "M")
        query = maybe_and(query, len(args) > 0 and len(vals) > 0)
        args.extend(vals)
        query += fragment

        fragment, vals = self.exact_matches(search_data.get("memories_exact", {}), "M")
        query = maybe_and(query, len(args) > 0 and len(vals) > 0)
        args.extend(vals)
        query += fragment

        fragment, vals = self.triples(search_data.get("triples", []), table)
        query = maybe_and(query, len(args) > 0 and len(vals) > 0)
        args.extend(vals)
        query += fragment

        if ignore_self:
            query += " AND {}.uuid !=?".format(table)
            args.append(self.self_memid)
        return query, args

    # flag (default) so that it makes a copy of speaker_look etc so that if the searcher is called
    # later so it doesn't return the new position of the agent/speaker/speakerlook
    # how to parse this distinction?
    def handle_special(self, agent_memory, search_data):
        d = search_data.get("special")
        if not d:
            return []
        if d.get("SPEAKER"):
            return [agent_memory.get_player_by_eid(d["SPEAKER"])]
        if d.get("SPEAKER_LOOK"):
            memids = agent_memory._db_read_one(
                'SELECT uuid FROM ReferenceObjects WHERE ref_type="attention" AND type_name=?',
                d["SPEAKER_LOOK"],
            )
            if memids:
                memid = memids[0]
                mem = agent_memory.get_location_by_id(memid)
                return [mem]
        if d.get("AGENT") is not None:
            return [agent_memory.get_player_by_eid(d["AGENT"])]
        if d.get("DUMMY"):
            return [d["DUMMY"]]
        return []

    def search(self, agent_memory, search_data=None) -> List["MemoryNode"]:  # noqa T484
        """Find memories matching the given filters
        search_data has children:
            "base_table", value is a string with a table name.  if not specified, the
                  base table is ReferenceObjects
            "base_range", dict, with keys "min<column_name>" or "max<column_name>",
                  (that is the string "min" prepended to the column name)
                  and float values vmin and vmax respectively.
                  <column_name> is any column in the base table that
                  is a numerical value.  filters on rows satisfying the inequality
                  <column_entry> > vmin or <column_entry> < vmax
            "base_exact", dict,  with keys "<column_name>"
                  <column_name> is any column in the base table
                  checks exact matches to the value
            "memories_range" and "memories_exact" are the same, but columns in the Memories table
            "triples" list [t0, t1, ...,, tm].  each t in the list is a dict
                  with form t = {"pred_text": <pred>, "obj_text": <obj>}
                  or t = {"pred_text": <pred>, "obj": <obj_memid>}
                  currently returns memories with all triples matched
        """
        if not search_data:
            search_data = self.search_data
        assert search_data
        search_data["base_table"] = search_data.get("base_table", "ReferenceObjects")
        self.search_data = search_data
        if search_data.get("special"):
            return self.handle_special(agent_memory, search_data)

        # FIXME more careful handling of "SELF",
        # rn you can only get it if you ask for it specfically
        ignore_self = "SELF" not in [t.get("obj_text", "") for t in search_data.get("triples", [])]
        query, args = self.get_query(search_data, ignore_self=ignore_self)

        # for debug:
        self.query = query
        self.query_args = args

        memids = [m[0] for m in agent_memory._db_read(query, *args)]
        return [agent_memory.get_mem_by_id(memid) for memid in memids]


# TODO subclass for filters that return at most one memory,value?
# TODO base_query instead of table
class MemoryFilter:
    def __init__(self, agent_memory, table="ReferenceObjects", preceding=None):
        """
        An object to search an agent memory, or to filter memories.

        args:
            agent_memory: and AgentMemory object
            table (str): a base table for the search, defining the "universe".
                Should be a table name from the memory schema (and is allowed to be
                the base memory table)
            preceding (MemoryFilter): if preceding is not None, this MemoryFilter will
                operate on the output of preceding

        the subclasses of MemoryFilter define three methods, .filter(memids, values)  and .search()
        and a __call__(memids=None, values=None)
        filter returns a subset of the memids and a matching subset of (perhaps transformed) vals
        search takes no input; and instead uses all memories in its table as "input"

        The standard interface to the MemoryFilter should be through the __call__
        if the __call__ gets no inputs, its a .search(); otherwise its a .filter on the value and memids
        """
        self.memory = agent_memory
        self.table = table
        self.head = None
        self.is_tail = True
        self.preceding = None
        if preceding:
            self.append(preceding)

    # SO ugly whole object should be a tree or deque, nothing stops previous filters from breaking chain etc.
    # FIXME
    # appends F to right (headwards) of self:
    # self will run on the output of F
    def append(self, F):
        if not self.is_tail:
            raise Exception("don't use MemoryFilter.append when MemoryFilter is not the tail")
        F.is_tail = False
        if not self.head:
            self.preceding = F
        else:
            # head is not guaranteed to be correct except at tail! (middle filters will be wrong)
            self.head.preceding = F
        self.head = F.head or F

    def all_table_memids(self):
        cmd = "SELECT uuid FROM " + self.table
        return [m[0] for m in self.memory._db_read(cmd)]

    # returns a list of memids, a list of vals
    # no input
    # search DOES NOT respect preceding; use the call if you want to respect preceding
    def search(self):
        if not self.preceding:
            all_memids = self.all_table_memids()
            return all_memids, [None] * len(all_memids)
        return [], []

    # inputs a list of memids, a list of vals,
    # returns a list of memids, a list of vals,
    def filter(self, memids, vals):
        return memids, vals

    def __call__(self, mems=None, vals=None):
        if self.preceding:
            mems, vals = self.preceding(mems=mems, vals=vals)
        if mems is None:
            # specifically excluding the case where mems=[]; then should filter
            return self.search()
        else:
            return self.filter(mems, vals)

    def _selfstr(self):
        return self.__class__.__name__

    def __repr__(self):
        if self.preceding:
            return self._selfstr() + " <-- " + str(self.preceding)
        else:
            return self._selfstr()


class MemidList(MemoryFilter):
    def __init__(self, agent_memory, memids):
        super().__init__(agent_memory)
        self.memids = memids

    def search(self):
        return self.memids, [None] * len(self.memids)

    def filter(self, memids, vals):
        mem_dict = dict(zip(memids, vals))
        filtered_memids = list(set.intersection(set(memids), set(self.memids)))
        filtered_vals = [mem_dict[m] for m in filtered_memids]
        return filtered_memids, filtered_vals


class NoneTransform(MemoryFilter):
    def __init__(self, agent_memory):
        super().__init__(agent_memory)

    def search(self):
        all_memids = self.all_table_memids()
        return all_memids, [None] * len(all_memids)

    def filter(self, memids, vals):
        return memids, [None] * len(memids)


# FIXME counting blocks in MC will still fail!!!
class CountTransform(MemoryFilter):
    def __init__(self, agent_memory):
        super().__init__(agent_memory)

    def search(self):
        all_memids = self.all_table_memids()
        return all_memids, [len(all_memids)] * len(all_memids)

    def filter(self, memids, vals):
        return memids, [len(memids)] * len(memids)


class ApplyAttribute(MemoryFilter):
    def __init__(self, agent_memory, attribute):
        super().__init__(agent_memory)
        self.attribute = attribute

    def search(self):
        all_memids = self.all_table_memids()
        return all_memids, self.attribute([self.memory.get_mem_by_id(m) for m in all_memids])

    def filter(self, memids, vals):
        return memids, self.attribute([self.memory.get_mem_by_id(m) for m in memids])

    def _selfstr(self):
        return "Apply " + str(self.attribute)


class RandomMemorySelector(MemoryFilter):
    def __init__(self, agent_memory, same="ALLOWED", n=1):
        super().__init__(agent_memory)
        self.n = n
        self.same = same

    def search(self):
        all_memids = self.all_table_memids()
        idxs = random_subsample_idx(len(all_memids), self.n, same=self.same)
        return [all_memids[i] for i in idxs], [None for i in idxs]

    def filter(self, memids, vals):
        idxs = random_subsample_idx(len(memids), self.n, same=self.same)
        return [memids[i] for i in idxs], [vals[i] for i in idxs]


class ExtremeValueMemorySelector(MemoryFilter):
    def __init__(self, agent_memory, polarity="argmax", ordinal=1):
        super().__init__(agent_memory)
        # polarity is "argmax" or "argmin"
        self.polarity = polarity

    # should this give an error? probably it should
    def search(self):
        all_memids = self.all_table_memids()
        i = torch.randint(len(all_memids), (1,)).item()
        return [all_memids[i]], [None]

    # FIXME!!!! do ordinals not 1
    def filter(self, memids, vals):
        if not memids:
            return [], []
        if self.polarity == "argmax":
            try:
                i = torch.argmax(torch.Tensor(vals)).item()
            except:
                raise Exception("are these values numbers?  trying to argmax them")
        else:
            try:
                i = torch.argmin(torch.Tensor(vals)).item()
            except:
                raise Exception("are these values numbers?  trying to argmin them")

        return [memids[i]], [vals[i]]

    def _selfstr(self):
        return self.polarity


class LogicalOperationFilter(MemoryFilter):
    def __init__(self, agent_memory, searchers):
        super().__init__(agent_memory)
        self.searchers = searchers
        if not self.searchers:
            raise Exception("empty filter list input into LogicalOperationFilter constructor")


class AndFilter(LogicalOperationFilter):
    def __init__(self, agent_memory, searchers):
        super().__init__(agent_memory, searchers)

    # TODO more efficient?
    # TODO unhashable values
    def search(self):
        N = len(self.searchers)
        mems, vals = self.searchers[0].search()
        for i in range(1, N):
            mems, vals = self.searchers[i].filter(mems, vals)
        return mems, vals

    def filter(self, mems, vals):
        for f in self.searchers:
            mems, vals = f.filter(mems, vals)
        return mems, vals


class OrFilter(LogicalOperationFilter):
    def __init__(self, agent_memory, searchers):
        super().__init__(agent_memory, searchers)

    # TODO more efficient?
    # TODO what to do if same memid has two different values? current version is not commutative
    # TODO warn/error if this has no previous?
    def search(self):
        all_mems = []
        vals = []
        for f in self.searchers:
            mems, v = f.search()
            all_mems.extend(mems)
            vals.extend(v)
        return self.filter(mems, vals)

    def filter(self, memids, vals):
        outmems = {}
        for i in range(len(memids)):
            outmems[memids[i]] = vals[i]
        memids, vals = outmems.items()
        return list(memids), list(vals)


class NotFilter(LogicalOperationFilter):
    def __init__(self, agent_memory, searchers):
        super().__init__(agent_memory, searchers)

    def search(self):
        cmd = "SELECT uuid FROM " + self.base_filters.table
        all_memids = self.memory._db_read(cmd)
        out_memids = list(set(all_memids) - set(self.searchers[0].search()))
        out_vals = [None] * len(out_memids)
        return out_memids, out_vals

    def filter(self, memids, vals):
        mem_dict = dict(zip(memids, vals))
        p_memids, _ = self.searchers[0].filter(memids, vals)
        filtered_memids = list(set(memids) - set(p_memids))
        filtered_vals = [mem_dict[m] for m in filtered_memids]
        return filtered_memids, filtered_vals


# FIXME combine with MemidList
class FixedMemFilter(MemoryFilter):
    def __init__(self, agent_memory, memid):
        super().__init__(agent_memory)
        self.memid = memid

    def search(self):
        return [self.memid], [None]

    def filter(self, memids, vals):
        try:
            i = memids.index(self.memid)
            return [memids[i]], vals[i]
        except:
            return [], []


class ComparatorFilter(MemoryFilter):
    def __init__(self, agent_memory, comparator_attribute):
        super().__init__(agent_memory)
        self.comparator = comparator_attribute

    def search(self):
        cmd = "SELECT uuid FROM " + self.base_filters.table
        all_memids = self.memory._db_read(cmd)
        return self.filter(all_memids, [None] * len(all_memids))

    def filter(self, memids, vals):
        mems = [self.memory.get_mem_by_id(m) for m in memids]
        T = self.comparator(mems)
        return (
            [memids[i] for i in range(len(mems)) if T[i]],
            [vals[i] for i in range(len(mems)) if T[i]],
        )


class BasicFilter(MemoryFilter):
    def __init__(self, agent_memory, search_data):
        super().__init__(agent_memory)
        self.search_data = search_data
        self.sql_interface = BasicMemorySearcher(search_data=search_data)

    def get_memids(self):
        return [m.memid for m in self.sql_interface.search(self.memory)]

    def search(self):
        memids = self.get_memids()
        return memids, [None] * len(memids)

    def filter(self, memids, vals):
        acceptable_memids = self.get_memids()
        filtered_memids = [memids[i] for i in range(len(memids)) if memids[i] in acceptable_memids]
        filtered_vals = [vals[i] for i in range(len(memids)) if memids[i] in acceptable_memids]
        return filtered_memids, filtered_vals

    def _selfstr(self):
        return "Basic: (" + str(self.search_data) + ")"


if __name__ == "__main__":
    search_data = {
        "ref_obj_range": {"minx": 3},
        "memories_exact": {"create_time": 1},
        "triples": [
            {"pred_text": "has_tag", "obj_text": "cow"},
            {"pred_text": "has_name", "obj_text": "eddie"},
        ],
    }
