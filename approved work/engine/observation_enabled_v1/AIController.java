package aiinterface;

import java.util.LinkedList;

import informationcontainer.RoundResult;
import setting.LaunchSetting;
import struct.AudioData;
import struct.FrameData;
import struct.GameData;
import struct.Key;
import struct.ScreenData;

/**
 * AIのスレッドや処理を管理するクラス．
 */
public class AIController extends Thread implements ControllerInterface {

    /**
     * AIに実装すべきメソッドを定義するインタフェース．
     */
    private AIInterface ai;
    
    //private GameData gameData;

    /**
     * The character's side flag.<br>
     * {@code true} if the character is P1, or {@code false} if P2.
     */
    private boolean playerNumber;

    /**
     * 対戦が始まっているかどうかを表すフラグ．
     */
    private boolean isFighting;

    /**
     * 入力されたキー．
     */
    private Key key;

    /**
     * 遅れフレーム．
     */
    private final static int DELAY = 15;

    /**
     * フレームデータを格納するリスト．
     */
    private LinkedList<FrameData> framesData;

    /**
     * 画面情報を格納したデータ．
     */
    private ScreenData screenData;

    private AudioData audioData;

    /**
     * 各AIの処理を同時に始めるための同期用オブジェクト．
     */
    private Object waitObj;
    
    private boolean roundEndFlag;
    private RoundResult roundResult;
    
    //private List<Double> durations = new ArrayList<>();

    /**
     * 引数に指定されたAIインタフェースをセットし，AIControllerを初期化するクラスコンストラクタ．
     *
     * @param ai AIに実装すべきメソッドを定義するインタフェース
     * @see AIInterface
     */
    public AIController(AIInterface ai) {
        this.ai = ai;
    }
    /**
     * 引数で与えられたパラメータをセットし，初期化を行う．
     *
     * @param waitFrame    各AIの処理を同時に始めるための同期用オブジェクト
     * @param gameData     ステージの画面幅や最大HPなどの，ゲーム内で不変の情報を格納したクラスのインスタンス
     * @param playerNumber the character's side flag.<br>
     *                     {@code true} if the character is P1, or {@code false} if P2.
     * @see GameData
     */
    public void initialize(Object waitFrame, GameData gameData, boolean playerNumber) {
        this.waitObj = waitFrame;
        this.playerNumber = playerNumber;
        this.key = new Key();
        this.framesData = new LinkedList<FrameData>();
        this.clear();
        this.isFighting = true;
        this.roundEndFlag = false;
        
		GameData visibleGameData = shouldMaskSyntheticNames(playerNumber)
				? gameData.withSyntheticBaseCharacterNames()
				: gameData;
		emitSyntheticNameMaskAudit(gameData, visibleGameData, playerNumber);
		this.ai.initialize(visibleGameData, playerNumber);
	}

	/**
	 * The compatibility view is launch-scoped and side-specific. It is off by default,
	 * so learner and research socket interfaces continue to receive true synthetic names.
	 */
	private static boolean shouldMaskSyntheticNames(boolean playerNumber) {
		String configured = System.getProperty("fightingice.syntheticNameMaskSides", "");
		String requested = playerNumber ? "P1" : "P2";
		for (String token : configured.split(",")) {
			String value = token.trim().toUpperCase();
			if (value.equals("BOTH") || value.equals(requested)) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Validation-only, behaviour-neutral boundary audit.  It records the true
	 * engine GameData and the exact controller-facing copy immediately before
	 * delegation.  The production masking operation itself is unchanged.
	 */
	private static void emitSyntheticNameMaskAudit(GameData actual, GameData visible, boolean playerNumber) {
		try {
			System.out.println("NAME_MASK_AUDIT"
					+ "|controller_side=" + (playerNumber ? "P1" : "P2")
					+ "|mask_requested=" + shouldMaskSyntheticNames(playerNumber)
					+ "|actual_p1=" + actual.getCharacterName(true)
					+ "|actual_p2=" + actual.getCharacterName(false)
					+ "|visible_p1=" + visible.getCharacterName(true)
					+ "|visible_p2=" + visible.getCharacterName(false)
					+ "|actual_motion_p1=" + motionDigest(actual.getMotionData(true))
					+ "|actual_motion_p2=" + motionDigest(actual.getMotionData(false))
					+ "|visible_motion_p1=" + motionDigest(visible.getMotionData(true))
					+ "|visible_motion_p2=" + motionDigest(visible.getMotionData(false))
					+ "|audit_action=" + System.getProperty("fightingice.auditAction", "")
					+ "|audit_field=" + System.getProperty("fightingice.auditField", "")
					+ "|actual_audit_value_p1=" + dynamicMechanicValue(actual.getMotionData(true))
					+ "|actual_audit_value_p2=" + dynamicMechanicValue(actual.getMotionData(false))
					+ "|visible_audit_value_p1=" + dynamicMechanicValue(visible.getMotionData(true))
					+ "|visible_audit_value_p2=" + dynamicMechanicValue(visible.getMotionData(false))
					+ "|actual_signature_p1=" + selectedMechanicSignature(actual.getMotionData(true))
					+ "|actual_signature_p2=" + selectedMechanicSignature(actual.getMotionData(false))
					+ "|visible_signature_p1=" + selectedMechanicSignature(visible.getMotionData(true))
					+ "|visible_signature_p2=" + selectedMechanicSignature(visible.getMotionData(false)));
		} catch (Exception exception) {
			System.out.println("NAME_MASK_AUDIT_ERROR|controller_side="
					+ (playerNumber ? "P1" : "P2") + "|error="
					+ exception.getClass().getName() + ":" + exception.getMessage());
		}
	}

	private static String dynamicMechanicValue(java.util.ArrayList<struct.MotionData> motions) {
		String wantedAction = System.getProperty("fightingice.auditAction", "");
		String wantedField = System.getProperty("fightingice.auditField", "");
		for (struct.MotionData motion : motions) {
			if (!wantedAction.equals(motion.getActionName())) continue;
			switch (wantedField) {
				case "frameNumber": return Integer.toString(motion.getFrameNumber());
				case "speedX": return Integer.toString(motion.getSpeedX());
				case "speedY": return Integer.toString(motion.getSpeedY());
				case "attack.hitAreaLeft": return Integer.toString(motion.getAttackHitArea().getLeft());
				case "attack.hitAreaRight": return Integer.toString(motion.getAttackHitArea().getRight());
				case "attack.hitAreaUp": return Integer.toString(motion.getAttackHitArea().getTop());
				case "attack.hitAreaDown": return Integer.toString(motion.getAttackHitArea().getBottom());
				case "attack.speedX": return Integer.toString(motion.getAttackSpeedX());
				case "attack.speedY": return Integer.toString(motion.getAttackSpeedY());
				case "attack.StartUp": return Integer.toString(motion.getAttackStartUp());
				case "attack.Active": return Integer.toString(motion.getAttackActive());
				case "attack.HitDamage": return Integer.toString(motion.getAttackHitDamage());
				case "attack.GuardDamage": return Integer.toString(motion.getAttackGuardDamage());
				case "attack.ImpactX": return Integer.toString(motion.getAttackImpactX());
				case "attack.ImpactY": return Integer.toString(motion.getAttackImpactY());
				case "attack.AttackType": return Integer.toString(motion.getAttackType());
				case "cancelAbleFrame": return Integer.toString(motion.getCancelAbleFrame());
				case "cancelAbleMotionLevel": return Integer.toString(motion.getCancelAbleMotionLevel());
				case "motionLevel": return Integer.toString(motion.getMotionLevel());
				default: return "UNSUPPORTED_FIELD";
			}
		}
		return "ACTION_NOT_FOUND";
	}

	private static String motionDigest(java.util.ArrayList<struct.MotionData> motions) throws Exception {
		java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
		for (struct.MotionData motion : motions) {
			struct.HitArea character = motion.getCharacterHitArea();
			struct.HitArea attack = motion.getAttackHitArea();
			String row = motion.getActionName() + "," + motion.getFrameNumber() + ","
					+ motion.getSpeedX() + "," + motion.getSpeedY() + ","
					+ area(character) + "," + motion.getState() + "," + area(attack) + ","
					+ motion.getAttackSpeedX() + "," + motion.getAttackSpeedY() + ","
					+ motion.getAttackStartUp() + "," + motion.getAttackActive() + ","
					+ motion.getAttackHitDamage() + "," + motion.getAttackGuardDamage() + ","
					+ motion.getAttackStartAddEnergy() + "," + motion.getAttackHitAddEnergy() + ","
					+ motion.getAttackGuardAddEnergy() + "," + motion.getAttackGiveEnergy() + ","
					+ motion.getAttackImpactX() + "," + motion.getAttackImpactY() + ","
					+ motion.getAttackGiveGuardRecov() + "," + motion.getAttackType() + ","
					+ motion.isAttackDownProp() + "," + motion.getCancelAbleFrame() + ","
					+ motion.getCancelAbleMotionLevel() + "," + motion.getMotionLevel() + ","
					+ motion.isControl() + "," + motion.isLandingFlag() + "\n";
			digest.update(row.getBytes(java.nio.charset.StandardCharsets.UTF_8));
		}
		StringBuilder hex = new StringBuilder();
		for (byte value : digest.digest()) {
			hex.append(String.format("%02x", value & 0xff));
		}
		return hex.toString();
	}

	private static String area(struct.HitArea value) {
		return value == null ? "null" : value.getLeft() + ":" + value.getRight() + ":" + value.getTop() + ":" + value.getBottom();
	}

	private static String selectedMechanicSignature(java.util.ArrayList<struct.MotionData> motions) {
		String[] names = {"AIR_A", "STAND_D_DF_FA", "CROUCH_A", "STAND_D_DB_BB", "STAND_F_D_DFB"};
		StringBuilder result = new StringBuilder();
		for (String name : names) {
			for (struct.MotionData motion : motions) {
				if (name.equals(motion.getActionName())) {
					if (result.length() > 0) result.append(";");
					result.append(name).append(":frame=").append(motion.getFrameNumber())
							.append(":startup=").append(motion.getAttackStartUp())
							.append(":damage=").append(motion.getAttackHitDamage())
							.append(":asx=").append(motion.getAttackSpeedX())
							.append(":asy=").append(motion.getAttackSpeedY())
							.append(":ix=").append(motion.getAttackImpactX())
							.append(":iy=").append(motion.getAttackImpactY());
					break;
				}
			}
		}
		return result.toString();
	}
    
    public Key input() {
    	return this.key;
    }
    
    @Override
    public void run() {
        while (isFighting) {
            synchronized (this.waitObj) {
                try {
                    this.waitObj.wait();
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
            
            if (!isFighting) break;
            
            if (this.roundEndFlag) {
            	this.ai.roundEnd(roundResult);
            	this.roundEndFlag = false;
            	this.roundResult = null;
            } else {
            	boolean isControl;

                try {
                    isControl = this.getLatestFrameData().getCharacter(this.playerNumber).isControl();
                } catch (NullPointerException e) {
                    // while game is not started
                    isControl = false;
                }

                FrameData frameData = this.removeOldestFrameData();
                
                // screen raw data isn't provided to sound-only AI
    	        if (!LaunchSetting.noVisual[this.playerNumber ? 0: 1]){
    	            this.ai.getScreenData(this.screenData);
    	        } else {
    	        	frameData.removeVisualData();
    	        }
            	this.ai.getInformation(frameData, isControl);
	        this.ai.getNonDelayFrameData(this.getLatestFrameData());
    	        this.ai.getAudioData(this.audioData);
    	        this.ai.processing();
    	        this.setInput(this.ai.input());
            }
	        
	        ThreadController.getInstance().notifyEndAIProcess(this.playerNumber);
        }
    }

    /**
     * AIからの入力情報を返す．<br>
     * 入力情報が無ければ空のキーを返す．
     *
     * @return AIからの入力情報
     * @see Key
     */
    public synchronized Key getInput() {
        if (this.key != null) {
            return this.key;
        } else {
            return new Key();
        }
    }

    /**
     * AIからの入力情報をセットする．
     *
     * @param key AIからの入力情報
     */
    public synchronized void setInput(Key key) {
        this.key = new Key(key);
    }

    /**
     * 対戦処理後のフレームデータをリストにセットする．<br>
     * リストのサイズがDELAYより大きければ，最も古いフレームデータを削除する．
     *
     * @param fd 対戦処理後のフレームデータ
     * @see FrameData
     */
    public synchronized void setFrameData(FrameData fd, ScreenData sd, AudioData ad) {
        if (!fd.getEmptyFlag()) {
            this.framesData.addLast(new FrameData(fd));
        } else {
            this.framesData.addLast(new FrameData());
        }

        while (this.framesData.size() > DELAY) {
            this.framesData.removeFirst();
        }

        this.screenData = new ScreenData(sd);
        this.audioData = new AudioData(ad);
    }

    /**
     * Read the newest queued frame while holding the same monitor used by setFrameData() and
     * clear().  clear() temporarily makes the LinkedList empty before restoring its DELAY dummy
     * frames, so an unsynchronised getLast() can otherwise throw NoSuchElementException.
     */
    private synchronized FrameData getLatestFrameData() {
        return this.framesData != null && !this.framesData.isEmpty()
                ? this.framesData.getLast()
                : new FrameData();
    }

    /**
     * Remove the delayed frame atomically, or return the same dummy value used by the old empty
     * branch.  Keeping this as a separate operation preserves the original interleaving point
     * before the later non-delay read.
     */
    private synchronized FrameData removeOldestFrameData() {
        return this.framesData != null && !this.framesData.isEmpty()
                ? new FrameData(this.framesData.removeFirst())
                : new FrameData();
    }

    /**
     * リストに格納してあるフレームデータを削除する．<br>
     * その後，DELAY-1個の空のフレームデータをリストに格納する．
     */
    public synchronized void clear() {
        if (this.framesData != null) {
            this.framesData.clear();

            while (this.framesData.size() < DELAY) {
                this.framesData.add(new FrameData());
            }
        }

        this.screenData = new ScreenData();
        this.audioData = new AudioData();
    }
    
    /**
     * 現在のラウンド終了時の結果をAIに渡す．
     *
     * @param roundResult 現在のラウンド終了時の結果
     * @see RoundResult
     */
    public synchronized void informRoundResult(RoundResult roundResult) {
    	this.roundEndFlag = true;
    	this.roundResult = roundResult;
    }

    /**
     * 対戦が終わったことを通知し，AIの終了処理を行う．
     */
    public synchronized void gameEnd() {
        this.isFighting = false;
        this.ai.close();
        synchronized (this.waitObj) {
            this.waitObj.notifyAll();
        }
    }
}
