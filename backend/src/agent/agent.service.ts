import { Injectable } from '@nestjs/common';
import { CheckpointerService } from '../checkpointer/checkpointer.service';
import { StateGraph, Annotation, END, START } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { BaseMessage, HumanMessage, AIMessage } from '@langchain/core/messages';

const AgentState = Annotation.Root({
  messages: Annotation<BaseMessage[]>({
    reducer: (x, y) => x.concat(y),
  }),
  plan: Annotation<string[]>({
    reducer: (_x, y) => y,
    default: () => [],
  }),
});

@Injectable()
export class AgentService {
  private graph: any;

  constructor(private readonly checkpointerService: CheckpointerService) {}

  async getGraph() {
    if (this.graph) return this.graph;

    const checkpointer = await this.checkpointerService.getCheckpointer();
    const llm = new ChatOpenAI({
      modelName: 'gpt-4o-mini',
      streaming: true,
      openAIApiKey: process.env.OPENAI_API_KEY,
    });

    const plannerNode = async (state: typeof AgentState.State) => {
      const lastMessage = state.messages[state.messages.length - 1];
      const content = lastMessage?.content?.toString() ?? '';
      const planResponse = await llm.invoke([
        new HumanMessage(
          `Create a numbered step-by-step plan (3-5 steps) for: "${content}". Return ONLY a JSON array of step strings, e.g. ["Step 1: ...", "Step 2: ..."]`,
        ),
      ]);
      let plan: string[] = [];
      try {
        const text = planResponse.content.toString();
        const match = text.match(/\[.*\]/s);
        if (match) plan = JSON.parse(match[0]);
      } catch {
        plan = ['Analyzing request...', 'Processing...', 'Generating response...'];
      }
      return { plan };
    };

    const responderNode = async (state: typeof AgentState.State) => {
      const messages = state.messages.map((m) =>
        m instanceof HumanMessage ? new HumanMessage(m.content) : new AIMessage(m.content),
      );
      const systemPrompt = state.plan.length
        ? `You are a helpful assistant. Follow this plan:\n${state.plan.map((s, i) => `${i + 1}. ${s}`).join('\n')}`
        : 'You are a helpful assistant.';
      const response = await llm.invoke([new HumanMessage(systemPrompt), ...messages]);
      return { messages: [new AIMessage(response.content)] };
    };

    const workflow = new StateGraph(AgentState)
      .addNode('planner', plannerNode)
      .addNode('responder', responderNode)
      .addEdge(START, 'planner')
      .addEdge('planner', 'responder')
      .addEdge('responder', END);

    this.graph = workflow.compile({ checkpointer });
    return this.graph;
  }
}
