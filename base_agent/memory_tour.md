# High level pipeline

This document is a high level walkthrough of memory and how it integrates with other droidet components.

We have 5 important components to think about when we think of a droidlet agent:

1. **Language understanding component** that takes in language and converts that to a partially executable program (we call these programs: *logical forms*).  Example:

```
Input: "go to the chair"

Output logical form: 
{
"dialogue_type": "HUMAN_GIVE_COMMAND", 
"action_sequence": [
    {"location": {
        "reference_object": {
             "filters": {
                    "triples": [{"pred_text": "has_name", "obj_text": "chair" }]}}},
     "action_type": "MOVE"
    }
   ]
}
```

2. **Interpreter** - this component takes in output of step #1 and tries to convert that into an executable program (we call this a *Task*) by interfacing with memory and filling in world specific information. For example:

```
Input:
{
"dialogue_type": "HUMAN_GIVE_COMMAND", 
"action_sequence": [
    {"location": {
        "reference_object": {
             "filters": {
                    "triples": [{"pred_text": "has_name", "obj_text": "chair" }]}}},
     "action_type": "MOVE"
    }
   ]
}

Output Task :
task_data = {"target": <Absolute coordinates of chair> , "action_dict": <Input from above>}
Move(agent, task_data)
```

To get from the input to the output, the interpreter needs to fill in missing details in the logical form by stepping through it. The way we do this is: the interpreter steps throuhg the logical form one key at a time, and asks for world-specific information from the memory (via the agent) if needed. Here, it first checks the `dialogue_type` (which is `HUMAN_GIVE_COMMAND`), then based on the `dialogue_type` it decides on how to read its siblings. In the example here, it first checks the the type of the `action` (which is `MOVE`) then based on action type it reads the children of the actions (`"location"` for a `MOVE` in this example).

While reading the nested dictionary, one key at a time, the interpreter decides when it needs to ask memory to populate some information from the world (in this case the exact coordinates of an object called `"chair"`). Assuming that the perception component is already populating the agent's memory with what it recognizes, we should have a way of extracting the absolute coordinates of a `"chair"` through the memory APIs.

3. Perception : We won't go into the details of this component but the high level idea here is to get information from the world and store it in memory. So detecting a `"chair"` here and storing its coordinates in memory. This component interfaces with the agent’s world.

4. Memory: This component is the nexus of information for all other systems - any information that needs to be stored for later use, any information that needs to be communicated between modules and any information about the state of the world. 

5. Task: These are things that cause and affect changes in the world. Tasks are small self contained actions that an agent can perform, example : jumping, moving from x to y, pointing etc. Tasks are platform specific and the under-the-hood implementation for a task can be different in different frameworks.

# Memory

This document dives into the current state of memory, the behind the scenes and the bridge between interpreter, memory and perception.

To start with, we have a concept of memory which is the nexus of all information needed in order for the system of modules explained above to work together.

In theory, **memory is a key-value store, where keys are unique identifiers and values are heterogenous memory objects or nodes**. Retrieving a record or a property of a record might sometimes require deep inspection, multiples levels of querying, and might require significant non-cachable computation at retrieval time.

For example, for the command: `"what is tallest thing I've made in the last 5 minutes ?"`. 
We first need to query memory for all the things **I** constructed in the **last 5 minutes**, then I need to extract the **height** property of each of those things and then **rank them in decreasing order** of height and **pick the first one**.

Note that some parts of the computation above are done outside the scope of querying a key-value store, for example: ranking on height and picking the first one - these are handled by the interpreter after getting the output from memory access APIs.

When we think of memory, there are few important components:
1. **The implementation** - the actual database structure that holds the information.
2. **Memory nodes** - The instance of a memory object.
3. **Interfacing with the database (AgentMemory)** - this provides all the high level memory APIs that enable database access. All the raw database queries reside here.  

Each of the bullets mentioned above can be extended by a new droidlet agent. 

Before we dive into the subsections about the components above, here is a pseudo code of how the memory access works in an agent right now:

**Example command : "how many shirts do you see"**
1. The agent process queries the semantic parsing model to get the logical form:
```python
lf = {
        "dialogue_type": "GET_MEMORY",
        "filters": {
            "output": "COUNT",
            "triples": [{"pred_text": "has_name", "obj_text": shirt}],
        }
    }
```
2. The agent's interpreter takes this logical form, checks that some information is being requested (dialogue_type: *`GET_MEMORY`*), then extracts the relevant sub dictionaries and calls the respective subinterpreters (in this case the subinterpreter for `"filters"`) to fill in missing information from memory (in this case : *number of shirts*). 
```python
filters_d = {
            "output": "COUNT",
            "triples": [{"pred_text": "has_name", "obj_text": shirt}],
        }
agent.interpreter.subinterpret["filters"](dummy_interpreter, "SPEAKER", filters_d)
```
3. The filters subinterpreter interacts with the *agent's memory API* to first get all the memories that have name : *"shirt"* and then performs a *count* operation on top of the list of memories to return the answer back to the speaker.

## Implementation of the key-value store

Right now we have implemented the key-value store using sqlite. We provide a base schema with droidlet [here](https://github.com/facebookresearch/droidlet/blob/main/base_agent/base_memory_schema.sql) which can be extended by a new agent depending on the agent's use case. For example, the craftassist agent extends this schema [here](https://github.com/facebookresearch/droidlet/blob/main/craftassist/agent/mc_memory_schema.sql) and locobot extends it [here](https://github.com/facebookresearch/droidlet/blob/main/locobot/agent/loco_memory_schema.sql). 
On a high level, we have two main categories of tables:
1. A main Memories table that tracks important metadata for all memory objects like : created time, updated time, node type etc. 
2. A lot of other tables that each represent a concept, for example : Chat, Player, Triples, NamedAbstraction etc. Each of these tables has their own attributes and things they track. 


## Memory Nodes

A memory node is an instance of a memory and can have its own attributes and functions.
We provide a set of base memory nodes [here](https://github.com/facebookresearch/droidlet/blob/main/base_agent/memory_nodes.py) that can be extended by any agent using droidlet. For example craftassist nodes are [here](https://github.com/facebookresearch/droidlet/blob/main/craftassist/agent/mc_memory_nodes.py) and locobot nodes are [here](https://github.com/facebookresearch/droidlet/blob/main/locobot/agent/loco_memory_nodes.py).

Each memory node is associated with a table in the database and exposes methods like : attribute getters, attribute setters and a create method. 


## Agent memory

This is the high level memory interface defined [here](https://github.com/facebookresearch/droidlet/blob/main/base_agent/sql_memory.py#L50) in the code, that acts as an operational interface for the database. 
This is the class that supports raw SQL database access for creating the tables, given the schema and then reading, writing and updates to the database.

In addition to SQL queries, this interface acts as a **high level memory API for the agent process** that involves any manipulation or access to the state of memory. This includes but is not limited to: *querying the current state of memory, updating the state, any deletion, upsert, loading environment information into memory, structured searches on tables, etc*

A droidlet agent can extend this class to add more capabilities as needed, based on the framework. 

Pseudo code for instantiating this class is:
```
memory = AgentMemory(db_file=":memory:",        # The database file
                    schema_paths=SCHEMAS,       # Path to the files containing the database schema
                    db_log_path=None,           # Path to where the database logs will be written
                    nodelist=NODELIST,          # List of memory nodes
                    agent_time=None             # A time object 
                    on_delete_callback=None     # callable to be run when a memory is deleted 
                    )
```
Once initiliazed with the schemas and memory nodes, this memory object now provides methods to interact with the underlying SQL implementation.


Examples of a few commonly used methods from this high level memory interface are :
1. Tagging a memory : 

`memory.tag(memid, "VOXEL_OBJECT")`
      
2. Fetching all memories that are, for example, blue in color:

`memory.get_triples(pred_text="has_color, obj_text="blue")`

3. Getting something directly from the table `"VoxelObjects"`:

`memory._db_read("SELECT x, y, z FROM VoxelObjects WHERE uuid=?", self.memid)`

4. Getting exactly one record from the table `"ReferenceObjects"` :

`
x, y, z = memory._db_read_one(
           "SELECT x, y, z FROM ReferenceObjects WHERE uuid=?", self.memid
       )
`

5. Inserting a new record into the table `"ReferenceObjects"` :

`
memory.db_write(
           "INSERT INTO ReferenceObjects(uuid, eid, x, y, z, yaw, pitch, ref_type, type_name, player_placed, agent_placed, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           memid,
           mob.entityId,
           mob.pos.x,
           mob.pos.y,
           mob.pos.z,
           mob.look.yaw,
           mob.look.pitch,
           "mob",
           mobtype,
           player_placed,
           agent_placed,
           memory.get_time(),
       )
`

6. Adding a new triple: 

`
memory.add_triple(subj=memid, pred_text="has_name", obj_text=mobtype)
`


Overall, to access anything from the state of database, there are two routes:
1. The conventional route: access the memory interface defined for the agent process as described above (`agent.memory.<high_level_memory_API_call>`)
2. Another route: Get the attributes of the memory nodes directly by using their getters and setters. 