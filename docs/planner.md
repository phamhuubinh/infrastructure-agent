# Planner Architecture

## 1. Role of the Planner  
The Planner is responsible for generating actionable strategies to test hypotheses, explore unknown areas, or refine existing knowledge. It selects the most effective sequence of steps based on the agent's current understanding of the environment, balancing exploration (investigating unknown regions) and exploitation (deepening understanding of confirmed patterns).

## 2. Separation from the Executor  
The Planner must be separated from the Executor to ensure modularity, scalability, and safety. The Planner focuses on high-level decision-making, while the Executor handles low-level task execution. This separation prevents execution errors from disrupting planning logic and allows independent development and testing of each component.

## 3. Information from the Knowledge Model  
The Planner receives structured data from the Knowledge Model, including:  
- **Entities**: Core components of the environment (e.g., systems, users, files).  
- **Relationships**: Interactions or connections between entities (e.g., dependencies, ownership).  
- **Attributes**: Properties of entities (e.g., metadata, values).  
- **Patterns**: Repeated structures or behaviors observed in the environment.  
- **Anomalies**: Unusual observations that deviate from established patterns.  
- **Historical Context**: Records of past observations, hypotheses, and outcomes.  

## 4. Output of the Planner  
The Planner produces a prioritized list of actions or tasks, such as:  
- "Investigate anomaly X by querying system logs."  
- "Validate hypothesis Y by executing test scenario Z."  
These plans are abstract and must be translated by the Executor into concrete operations.

## 5. Why the Planner Does Not Execute Actions  
The Planner should never execute actions directly because execution requires interaction with the environment (e.g., system APIs, hardware), which is the Executor's domain. This division ensures reliability, reusability, and the ability to adapt execution strategies without modifying planning logic.

## 6. Interaction with Other Components  
- **Knowledge Model**: Provides context for planning decisions.  
- **Executor**: Receives action plans and translates them into operations.  
- **Discovery Engine**: Informs the Planner of new observations or anomalies that may require investigation.  

The Planner is a critical link between the agent's understanding of the environment and its ability to take meaningful action.

## 7. Internal Planner Architecture  
The Planner operates through a structured internal process that ensures goals are met efficiently and adaptively. The key components and their interactions are as follows:

### 7.1. Goal  
The **Goal** represents the high-level objective derived from the Knowledge Model or external inputs. It defines what the Planner aims to achieve (e.g., "investigate anomaly X" or "validate hypothesis Y"). Goals are abstract and must be broken down into actionable steps.

### 7.2. Goal Queue  
The **Goal Queue** is a prioritized list of goals that the Planner must address. It is populated by the Knowledge Model (e.g., based on anomalies or unexplored areas) and updated dynamically as new information becomes available. The queue ensures that the Planner focuses on the most critical objectives first.

### 7.3. Candidate Actions  
**Candidate Actions** are potential steps that could be taken to achieve a goal. They are generated based on the current state of the Knowledge Model, historical context, and the nature of the goal. For example, if the goal is to "investigate anomaly X," candidate actions might include "query system logs" or "inspect related files."

### 7.4. Prioritization  
The **Prioritization** mechanism evaluates candidate actions based on criteria such as relevance to the goal, risk, resource requirements, and potential impact. It ensures that the most promising actions are selected for further processing. Prioritization may use heuristics or rules defined by the agent's architecture.

### 7.5. Planning  
The **Planning** component generates a sequence of actions (a "plan") that aligns with the goal and prioritized candidate actions. It considers constraints such as dependencies between actions, available resources, and potential conflicts. The plan is a logical sequence of steps that the Executor can later translate into concrete operations.

### 7.6. Plan Validation  
Before finalizing a plan, the **Plan Validation** process checks whether the proposed sequence of actions is feasible based on the current Knowledge Model. It verifies that all required entities, relationships, and attributes exist and are consistent with the agent's understanding of the environment. If validation fails, the Planner revisits earlier steps (e.g., prioritization or candidate action generation).

### 7.7. Replanning  
**Replanning** occurs when new information (e.g., from the Discovery Engine or Executor feedback) invalidates the current plan or goal. The Planner updates the Goal Queue, regenerates candidate actions, and re-evaluates prioritization to produce a revised plan. Replanning ensures that the Planner adapts to changes in the environment or knowledge state.

### Information Flow Between Components  
- The **Knowledge Model** provides goals, context, and constraints to the Planner.  
- The **Goal Queue** feeds into **Candidate Actions** generation.  
- **Prioritization** influences the **Planning** process.  
- **Plan Validation** may trigger **Replanning** if the plan is invalid.  
- The **Executor** receives the final plan and provides feedback (e.g., success/failure) that may trigger **Replanning** or updates to the **Knowledge Model**.  

This internal architecture ensures the Planner remains flexible, responsive, and aligned with the agent's evolving understanding of the environment.
