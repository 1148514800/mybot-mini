"""35 synthetic, read-only MCP tools; real stdio protocol, no network/files/shell."""
import asyncio
import json

from jsonschema import Draft202012Validator
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

CATEGORIES = {
    'project': ['list_project_tasks','get_project_task','search_project_tasks','list_project_milestones',
                'get_project_status','list_project_labels','list_project_members'],
    'documents': ['search_documents','get_document','list_document_sections','list_document_versions',
                  'get_document_outline','find_document_links','list_document_tags'],
    'code': ['list_code_symbols','get_code_symbol','search_code_references','summarize_code_file',
             'inspect_code_imports','list_code_modules','get_code_metrics'],
    'calendar': ['list_calendar_events','get_calendar_event','find_calendar_slots','list_calendar_calendars',
                 'get_calendar_day','search_calendar_events','list_calendar_labels'],
    'data': ['summarize_dataset','list_dataset_columns','get_dataset_stats','filter_dataset_rows',
             'group_dataset_rows','describe_dataset_schema','get_dataset_preview'],
}


def definitions():
    tools = []
    primary = {'project':('project','Project identifier; use mini for the fixed teaching project.'),
               'documents':('query','Literal document query, such as architecture; no semantic search.'),
               'code':('module','Synthetic module identifier; no real source files are opened.'),
               'calendar':('day','Synthetic calendar day identifier; no external calendar is accessed.'),
               'data':('dataset','Synthetic dataset identifier; no user dataset is read.')}
    for category,names in CATEGORIES.items():
        key,description = primary[category]
        properties = {key:{'type':'string','minLength':1,'maxLength':100,'description':description},
            'status':{'type':'string','enum':['pending','done','all'],'default':'pending',
                      'description':'Filter synthetic task status; ignored by categories without task states.'},
            'limit':{'type':'integer','minimum':1,'maximum':50,'default':10,
                     'description':'Maximum synthetic records returned; never expands access to external resources.'},
            'offset':{'type':'integer','minimum':0,'maximum':100,'default':0,
                      'description':'Offset within this fixed in-memory result, without remote pagination.'},
            'include_details':{'type':'boolean','default':False,
                               'description':'Include the fixed record details; this is a read-only operation.'},
            'format':{'type':'string','enum':['compact','detailed'],'default':'compact',
                      'description':'Choose the representation of the same synthetic data without changing its meaning.'},
            'labels':{'type':'array','items':{'type':'string','maxLength':50},'maxItems':5,
                      'description':'Optional exact labels for this teaching fixture; does not create labels or files.'},
            'sort':{'type':'string','enum':['id','title'],'default':'id',
                    'description':'Stable sorting by a known record field; arbitrary expressions are not accepted.'}}
        schema={'type':'object','properties':properties,'required':[key],'additionalProperties':False}
        for name in names:
            text = ('List pending project tasks and status for a project.' if name=='list_project_tasks' else
                    'Search documents by literal query in the synthetic architecture handbook.' if name=='search_documents' else
                    f'{name.replace("_"," ").capitalize()} in the synthetic {category} catalog; read-only teaching data.')
            tools.append(types.Tool(name=name,description=text,inputSchema=schema))
    return tools


DEFINITIONS = {tool.name:tool for tool in definitions()}


async def listing(ctx, params):return types.ListToolsResult(tools=list(DEFINITIONS.values()))


async def calling(ctx, params):
    definition=DEFINITIONS.get(params.name)
    arguments=params.arguments or {}
    if definition is None or not Draft202012Validator(definition.input_schema).is_valid(arguments):
        return types.CallToolResult(isError=True,content=[types.TextContent(text='Invalid synthetic request')])
    if params.name == 'list_project_tasks':
        records=[{'id':'TASK-1','title':'Review architecture','status':'pending'},
                 {'id':'TASK-2','title':'Write discovery tests','status':'pending'}]
        if arguments.get('status')=='done':records=[]
        result={'project':arguments['project'],'tasks':records}
    elif params.name == 'search_documents':
        result={'query':arguments['query'],'documents':[{'id':'DOC-1','title':'Architecture handbook'}]}
    else:
        result={'tool':params.name,'synthetic':True,'records':[{'id':'SYNTHETIC-1','title':'Teaching record'}]}
    return types.CallToolResult(content=[types.TextContent(text=json.dumps(result))])


server=Server('catalog-demo',on_list_tools=listing,on_call_tool=calling)


async def main():
    async with stdio_server() as streams:
        await server.run(*streams,server.create_initialization_options())


if __name__=='__main__':asyncio.run(main())
