package server;
import java.io.*;
import java.net.*;
import org.json.*;
import java.util.concurrent.*;
import java.util.ArrayList;

class ExitServerSignal extends Exception{
	public ExitServerSignal(String msg){
		super(msg);
	}
}

class DummyAgent implements Agent{
	public DummyAgent(){}
	public String toString(){return "Dummy";}
	public void newRound(State start){}
	public void see(Action act, State results){}
	public Action playCard(Card c){return null;}
}

class GameThread implements Callable<Void>{
	private int numPlayers;
	private DummyAgent[] agents;
	private Socket socket;
	private BufferedReader in;
	private PrintWriter out;
	private State gameState;
	private State[] playerStates;
	//standards for jsons
	//terminate every data entry with \n
	/*
	FROM CLIENT
	verification obj: {ver_str:"<string>", num_players:<2-4>}
	exit call: {ver_str:"<string>", exit_server:true} (must be the first call)
	function call: {request:true, func_name:"<function>", parameters:{}}
	return val:{request:false, rv:<rv>}
	FROM SERVER
	verification obj: {ver_str: "<string>"}
	function call: {request:true, func_name:"<function>", parameters:{}}
	return val:{request:false, rv:<rv>}
	scores:{request:false, scores:[]}
	*/
	GameThread(Socket socket) throws InterruptedException{
		try{
			this.socket = socket;
			this.in = new BufferedReader(new InputStreamReader(socket.getInputStream()));
			this.out = new PrintWriter(socket.getOutputStream(), true);
		}
		catch(IOException e){
			throw new InterruptedException(e.toString());
		}
	}
	public Void call() throws ExitServerSignal, IOException{
		try{
			if(!verifyConnection()){
				System.err.println("Illegal Connection...kicking client");
				socket.close();
			}
			System.out.println("Socket was verified successfully");
			System.out.printf("Running game with %d players\n", numPlayers);
			boolean gameOver = false;
			int winner = 0;
			Agent[] agents = new Agent[numPlayers];
			for(int i = 0; i < numPlayers; ++i)
				agents[i] = new DummyAgent();
			gameState = new State(new java.util.Random(System.currentTimeMillis()), agents);
			playerStates = new State[numPlayers];
			while(!gameState.gameOver()){
				for(int i = 0; i < numPlayers; ++i){
					playerStates[i] = gameState.playerState(i);
					requestNewRound(i);
				}
				while(!gameState.roundOver()){
					Card topCard = gameState.drawCard();
					Action act = requestAction(gameState.nextPlayer(), topCard);
					try{
						gameState.update(act, topCard);
					}
					catch(IllegalActionException e){
						throw new IOException("ILLEGAL ACTION PERFORMED BY PLAYER "+agents[gameState.nextPlayer()]);
					}
					for(int i = 0; i < numPlayers; ++i)
						requestSee(i);
				}
				gameState.newRound();
			}
			int[] scores = new int[numPlayers];
			for(int i = 0; i < numPlayers; ++i)
				scores[i] = gameState.score(i);
			sendScores(scores);
			socket.close();
		}
		catch(IllegalActionException e){
			try{
				socket.close();
			}
			catch(IOException e2){/*do nothing*/}
			//this is slightly hacky, will revise
			throw new IOException(e.getMessage());
		}
		catch(IOException e){
			try{
				socket.close();
			}
			catch(IOException e2){/*do nothing*/}
			throw e;
		}
		catch(ExitServerSignal e){
			try{
				socket.close();
			}
			catch(IOException e2){/*do nothing*/}
			throw e;
		}
		return null;
	}

	boolean verifyConnection() throws IOException, ExitServerSignal{
		StringBuilder verificationStr = new StringBuilder();
		for(int i = 0; i < 20; ++i){
			if((int)(Math.random() * 2) == 0)
				verificationStr.append((char)(Math.random()*26 + 'a'));
			else
				verificationStr.append((char)(Math.random()*26 + 'A'));
		}
		Sha256 hasher = new Sha256();
		byte[] hashBytes = hasher.hash(verificationStr.toString().getBytes());
		//convert bytes to hex string
		StringBuilder expectedStrBuilder = new StringBuilder();
		for(int i = 0; i < hashBytes.length; ++i)
			expectedStrBuilder.append(String.format("%02x", hashBytes[i]));
		String expectedStr = expectedStrBuilder.toString();
		String toSend = "{\"ver_str\":\""+verificationStr.toString()+"\"}";
		out.println(toSend);
		socket.setSoTimeout(5000);
		try{
			String msg = in.readLine();
			JSONObject msgObj = new JSONObject(msg);
			if(!msgObj.getString("ver_str").equals(expectedStr))
				return false;
			try{
				if(msgObj.getBoolean("exit_server"))
					throw new ExitServerSignal("Called to exit");
			}
			catch(JSONException e){/*There was no exit call*/}
			numPlayers = msgObj.getInt("num_players");
			if(!(2 <= numPlayers && numPlayers <= 4)){
				return false;
			}
		}
		catch(SocketTimeoutException e){
			return false;
		}
		catch(IOException e){
			return false;
		}
		catch(JSONException e){
			return false;
		}
		return true;
	}

	void requestNewRound(int playerIndex) throws IOException{
		try{
			JSONObject request = new JSONObject();
			request.accumulate("request", true);
			request.accumulate("func_name", "new_round");
			JSONObject parameters = new JSONObject();
			parameters.accumulate("player_index", playerIndex);
			request.accumulate("parameters", parameters);
			out.println(request.toString());
			socket.setSoTimeout(5000);
			boolean returned = false;
			while(!returned){
				String msg = in.readLine();
				JSONObject msgObj = new JSONObject(msg);
				if(msgObj.getBoolean("request")){
					processRequest(playerIndex, msgObj);
				}
				else
					returned = true;
			}
		}
		catch(JSONException e){
			throw new IOException(e.getMessage());
		}
	}

	Action requestAction(int playerIndex, Card card) throws IOException{
		Action rv = null;
		try{
			JSONObject request = new JSONObject();
			request.accumulate("request", true);
			request.accumulate("func_name", "play_card");
			JSONObject parameters = new JSONObject();
			parameters.accumulate("player_index", playerIndex);
			int cardIndex = 0;
			for(; cardIndex < Card.values().length; ++cardIndex)
				if(card == Card.values()[cardIndex])
					break;
			parameters.accumulate("drawn", cardIndex);
			request.accumulate("parameters", parameters);
			out.println(request.toString());
			socket.setSoTimeout(5000);
			while(rv == null){
				String msg = in.readLine();
				JSONObject msgObj = new JSONObject(msg);
				if(msgObj.getBoolean("request")){
					processRequest(playerIndex, msgObj);
				}
				else
					rv = actionFromJSON(playerIndex, msgObj.getJSONObject("rv"));
			}
		}
		catch(JSONException e){
			throw new IOException(e.getMessage());
		}
		if(rv == null){
			throw new IOException("PLAYER SENT ILLEGAL MOVE");
		}
		return rv;
	}
	void requestSee(int playerIndex) throws IOException{
		try{
			JSONObject request = new JSONObject();
			request.accumulate("request", true);
			request.accumulate("func_name", "see");
			JSONObject parameters = new JSONObject();
			parameters.accumulate("player_index", playerIndex);
			request.accumulate("parameters", parameters);
			out.println(request.toString());
			socket.setSoTimeout(5000);
			boolean returned = false;
			while(!returned){
				String msg = in.readLine();
				JSONObject msgObj = new JSONObject(msg);
				if(msgObj.getBoolean("request")){
					processRequest(playerIndex, msgObj);
				}
				else
					returned = true;
			}
		}
		catch(JSONException e){
			throw new IOException(e.getMessage());
		}
	}
	void sendScores(int[] scores) throws IOException{
		try{
			JSONObject toSend = new JSONObject();
			toSend.accumulate("request", false);
			toSend.accumulate("scores", scores);
			out.println(toSend.toString());
		}
		catch(JSONException e){
			throw new IOException(e.getMessage());
		}
	}

	Action actionFromJSON(int playerIndex, JSONObject object) throws JSONException{
		Action rv = null;
		try{
			Card c = Card.values()[object.getInt("card")];
			int target;
			Card guess;
			switch(c){
			case GUARD:
				target = object.getInt("target");
				guess = Card.values()[object.getInt("guess")];
				rv = Action.playGuard(playerIndex, target, guess);
				break;
			case PRIEST:
				target = object.getInt("target");
				rv = Action.playPriest(playerIndex, target);
				break;
			case BARON:
				target = object.getInt("target");
				rv = Action.playBaron(playerIndex, target);
				break;
			case HANDMAID:
				rv = Action.playHandmaid(playerIndex);
				break;
			case PRINCE:
				target = object.getInt("target");
				rv = Action.playPrince(playerIndex, target);
				break;
			case KING:
				target = object.getInt("target");
				rv = Action.playKing(playerIndex, target);
				break;
			case COUNTESS:
				rv = Action.playCountess(playerIndex);
				break;
			case PRINCESS:
				rv = Action.playPrincess(playerIndex);
				break;
			}
		}
		catch(IllegalActionException e){
			rv = null;
		}
		return rv;
	}
	void processRequest(int playerIndex, JSONObject object) throws JSONException{
		String function = object.getString("func_name");
		JSONObject parameters = object.getJSONObject("parameters");
		JSONObject outputObj = null;
		if(function.equals("get_card")){
			//doesn't supply an rv if getCard returns null
			//don't like this, want to change to send null for the key rv
			Card buff = playerStates[playerIndex].getCard(parameters.getInt("player_index"));
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			if(buff != null){
				int rv = 0;
				for(; rv < Card.values().length; ++rv)
					if(buff == Card.values()[rv])
						break;
				outputObj.accumulate("rv", rv);
			}
		}
		else if(function.equals("legal_action")){
			Action act = actionFromJSON(playerIndex, parameters.getJSONObject("action"));
			Card drawn = Card.values()[parameters.getInt("drawn")];
			boolean rv = false;
			if(playerIndex < numPlayers){
				rv = playerStates[playerIndex].legalAction(act, drawn);
			}
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			outputObj.accumulate("rv", rv);
		}
		else if(function.equals("get_player_index")){
			int rv = playerStates[playerIndex].getPlayerIndex();
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			outputObj.accumulate("rv", rv);
		}
		else if(function.equals("eliminated")){
			boolean rv = playerStates[playerIndex].eliminated(parameters.getInt("player_index"));
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			outputObj.accumulate("rv", rv);
		}
		else if(function.equals("get_discards")){
			ArrayList<Integer> rv = new ArrayList<Integer>();
			java.util.Iterator<Card> discardIterator = playerStates[playerIndex].getDiscards(parameters.getInt("player_index"));
			while(discardIterator.hasNext()){
				Card cardBuff = discardIterator.next();
				int nextVal = 0;
				for(; nextVal < Card.values().length; ++nextVal)
					if(cardBuff == Card.values()[nextVal])
						break;
				rv.add(nextVal);
			}
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			outputObj.accumulate("rv", rv);
		}
		else if(function.equals("score")){
			int rv = playerStates[playerIndex].score(parameters.getInt("player_index"));
			outputObj = new JSONObject();
			outputObj.accumulate("request", false);
			outputObj.accumulate("rv", rv);
		}
		if(outputObj == null){
			throw new JSONException("Invalid request");
		}
		out.println(outputObj.toString());
	}
}

public class Server{
	private static Socket socket = null;
	private static ServerSocket server = null;
	private static BufferedReader in = null;
	private static int port = 15000;
	public static void main(String[] args) throws IOException{
		server = new ServerSocket(port);
		server.setSoTimeout(5000);
		System.out.println("Server started");
		ExecutorService executor = Executors.newCachedThreadPool();
		ArrayList<Future<Void>> gameThreads = new ArrayList<Future<Void>>();
		boolean running = true;
		while(running){
			try{
				socket = server.accept();
				Future<Void> thread = executor.submit(new GameThread(socket));
				gameThreads.add(thread);
			}
			catch (SocketTimeoutException e){/*don't add a new gamethread*/}
			catch (InterruptedException e){
				e.printStackTrace();
				running = false;
			}
			int delindex = 0;
			for(int i = 0; i < gameThreads.size(); ++i){
				Future<Void> threadResult = gameThreads.get(i);
				if(!threadResult.isDone()){continue;}
				try{
					threadResult.get();
				}
				catch(ExecutionException e){
					if(e.getMessage().contains("ExitServerSignal"))
						running = false;
					else
						System.err.println(e.getMessage());
				}
				catch(InterruptedException e){
					System.err.print(e);
				}
				gameThreads.set(i, gameThreads.get(delindex++));
			}
			gameThreads = new ArrayList<Future<Void>>(gameThreads.subList(delindex, gameThreads.size()));
		}
		try{
			server.close();
		}
		catch(SocketException e){
			System.err.print(e);
		}
		executor.shutdown();
		System.out.println("Server closed");
	}
}
